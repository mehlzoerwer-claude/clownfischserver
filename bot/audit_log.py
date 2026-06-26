#!/usr/bin/env python3
"""
🐠 Clownfischserver – Audit Trail (DSGVO Art. 5 + 32)
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0

Writes JSON-line entries for every privileged action.
Pseudonymized: stores only numeric Telegram user_ids, never usernames.

Compliance:
- Art. 5(1)(a) lawfulness/transparency: every action is recorded.
- Art. 5(1)(c) data minimization: numeric IDs only, command/result trimmed.
- Art. 5(1)(e) storage limitation: prune_old_logs() drops entries older
  than AUDIT_RETENTION_DAYS (default 90).
- Art. 32 integrity: append-only file, 0600 permissions.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# How much of a command/result we keep – longer payloads are truncated
# to honour data minimization. Configurable via env.
_MAX_DETAIL_LEN = int(os.getenv("AUDIT_MAX_DETAIL_LEN", "2000"))

# Lock for append writes – multiple coroutines may log concurrently.
_write_lock = threading.Lock()


def _default_audit_path() -> str:
    install_dir = os.getenv("INSTALL_DIR", "/opt/clownfischserver")
    return os.getenv("AUDIT_LOG_PATH", os.path.join(install_dir, "audit.jsonl"))


def _retention_days() -> int:
    try:
        return max(0, int(os.getenv("AUDIT_RETENTION_DAYS", "90")))
    except ValueError:
        return 90


def _trim(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_DETAIL_LEN:
        return value[:_MAX_DETAIL_LEN] + f"... (truncated, {len(value)} chars total)"
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_action(
    user_id: str | int | None,
    action: str,
    *,
    role: str | None = None,
    result: str = "ok",
    details: dict[str, Any] | None = None,
    path: str | None = None,
) -> None:
    """Append a single audit record. Never raises – audit failure must not
    break the bot."""
    entry: dict[str, Any] = {
        "ts": _now_iso(),
        "user_id": str(user_id) if user_id is not None else None,
        "action": action,
        "result": result,
    }
    if role:
        entry["role"] = role
    if details:
        entry["details"] = {k: _trim(v) for k, v in details.items()}

    target = path or _default_audit_path()
    try:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _write_lock:
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(line)
            try:
                os.chmod(target, 0o600)
            except OSError:
                # chmod can fail on non-POSIX FS (e.g. tests on Windows) –
                # the JSONL content is still written.
                pass
    except Exception as e:
        logger.error(f"Audit log write failed: {e}")


def log_shell(user_id, command: str, *, role: str | None = None,
              status: str = "executed", returncode: int | None = None,
              stderr: str | None = None, path: str | None = None) -> None:
    details: dict[str, Any] = {"command": command}
    if returncode is not None:
        details["returncode"] = returncode
    if stderr:
        details["stderr"] = stderr
    log_action(user_id, "shell.execute", role=role, result=status,
               details=details, path=path)


def log_shell_proposed(user_id, description: str, command: str,
                       role: str | None = None, dangerous: bool = False,
                       path: str | None = None) -> None:
    log_action(
        user_id,
        "shell.proposed",
        role=role,
        result="dangerous" if dangerous else "ok",
        details={"description": description, "command": command},
        path=path,
    )


def log_code(user_id, task: str, *, role: str | None = None,
             status: str = "ok", path: str | None = None) -> None:
    log_action(user_id, "code.run", role=role, result=status,
               details={"task": task}, path=path)


def log_approval(user_id, command: str, *, role: str | None = None,
                 approved: bool = True, path: str | None = None) -> None:
    log_action(
        user_id,
        "shell.approval",
        role=role,
        result="approved" if approved else "rejected",
        details={"command": command},
        path=path,
    )


def log_denied(user_id, action: str, *, role: str | None = None,
               reason: str = "insufficient_role",
               path: str | None = None) -> None:
    log_action(user_id, action, role=role, result="denied",
               details={"reason": reason}, path=path)


def prune_old_logs(path: str | None = None,
                   retention_days: int | None = None) -> int:
    """Rewrite the audit file, dropping entries older than retention_days.

    Returns the number of dropped lines. retention_days=0 disables pruning.
    Uses an atomic temp-file + rename so a crash mid-prune cannot corrupt
    the audit trail.
    """
    target = path or _default_audit_path()
    days = retention_days if retention_days is not None else _retention_days()
    if days <= 0 or not os.path.exists(target):
        return 0

    cutoff = time.time() - days * 86400
    tmp_path = target + ".prune.tmp"
    dropped = 0
    kept = 0

    try:
        with _write_lock:
            with open(target, "r", encoding="utf-8") as src, \
                 open(tmp_path, "w", encoding="utf-8") as dst:
                for line in src:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        record = json.loads(raw)
                        ts = record.get("ts", "")
                        # ISO 8601 – parse with fromisoformat (UTC suffix safe)
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if dt.timestamp() < cutoff:
                            dropped += 1
                            continue
                    except (ValueError, KeyError):
                        # Malformed line: keep it rather than silently dropping
                        # forensic evidence.
                        pass
                    dst.write(line if line.endswith("\n") else line + "\n")
                    kept += 1
            os.replace(tmp_path, target)
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
        logger.info(f"Audit prune: kept={kept} dropped={dropped} retention={days}d")
    except Exception as e:
        logger.error(f"Audit prune failed: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return 0

    return dropped
