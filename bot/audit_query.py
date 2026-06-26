#!/usr/bin/env python3
"""
🐠 Clownfischserver – Audit Trail Query (Phase 2b)
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0

Read-side companion to audit_log.py. Filters/sorts JSONL audit records for
the `/logs` admin command.

The query layer is intentionally separate from the writer so that:
- Tests can exercise filtering without touching real audit data.
- The writer stays append-only and minimal.
- Future query backends (SQLite, OpenSearch) can swap in without touching
  the writer.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _default_audit_path() -> str:
    install_dir = os.getenv("INSTALL_DIR", "/opt/clownfischserver")
    return os.getenv("AUDIT_LOG_PATH", os.path.join(install_dir, "audit.jsonl"))


def _parse_ts(record: dict) -> datetime | None:
    """Best-effort parse of the record's ts field. Returns None on
    malformed timestamps (caller decides how to handle)."""
    ts = record.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def read_all(path: str | None = None) -> list[dict]:
    """Load every audit record from the JSONL file. Malformed lines are
    skipped with a debug log (the writer keeps them for forensic purposes,
    but the query layer prefers a clean result set)."""
    target = path or _default_audit_path()
    if not os.path.exists(target):
        return []

    out: list[dict] = []
    try:
        with open(target, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug(f"audit_query: skipping malformed line")
                    continue
    except OSError as e:
        logger.error(f"audit_query: cannot read {target}: {e}")
        return []
    return out


def filter_records(
    records: Iterable[dict],
    *,
    user_id: str | int | None = None,
    action: str | None = None,
    action_prefix: str | None = None,
    result: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    """Apply filters and return matching records, newest first.

    Filters are AND-combined. None values are ignored. action/result match
    exactly; action_prefix matches if the record's action starts with it.
    """
    target_user = str(user_id) if user_id is not None else None

    matched: list[dict] = []
    for rec in records:
        if target_user is not None and rec.get("user_id") != target_user:
            continue
        if action is not None and rec.get("action") != action:
            continue
        if action_prefix is not None:
            rec_action = rec.get("action", "")
            if not isinstance(rec_action, str) or not rec_action.startswith(action_prefix):
                continue
        if result is not None and rec.get("result") != result:
            continue
        if since is not None or until is not None:
            dt = _parse_ts(rec)
            if dt is None:
                # Malformed ts – exclude when caller asked for a date window.
                continue
            if since is not None and dt < since:
                continue
            if until is not None and dt > until:
                continue
        matched.append(rec)

    # Newest first – stable sort by ts (records without ts go to the bottom).
    matched.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return matched


def query(
    *,
    user_id: str | int | None = None,
    action: str | None = None,
    action_prefix: str | None = None,
    result: str | None = None,
    days: int | None = None,
    limit: int = 20,
    path: str | None = None,
) -> list[dict]:
    """Convenience wrapper: read + filter in one call.

    `days` is a shortcut for `since = now - days`. limit clamps the
    returned record count (use limit=0 for no limit)."""
    since = None
    if days is not None and days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)
    records = read_all(path=path)
    matched = filter_records(
        records,
        user_id=user_id,
        action=action,
        action_prefix=action_prefix,
        result=result,
        since=since,
    )
    if limit and limit > 0:
        matched = matched[:limit]
    return matched


def format_record(rec: dict) -> str:
    """Render one audit record as a single compact line for Telegram."""
    ts = rec.get("ts", "?")
    # Trim ts down to HH:MM:SS or YYYY-MM-DD HH:MM:SS for readability.
    if isinstance(ts, str) and len(ts) >= 19:
        ts_short = ts[:19].replace("T", " ")
    else:
        ts_short = str(ts)
    uid = rec.get("user_id") or "—"
    action = rec.get("action", "?")
    result = rec.get("result", "?")
    role = rec.get("role")
    role_part = f" [{role}]" if role else ""

    details = rec.get("details") or {}
    detail_str = ""
    if isinstance(details, dict):
        # Pick the single most-informative key per common action.
        for key in ("command", "task", "reason", "snapshot", "method", "tier"):
            if key in details:
                val = str(details[key])
                if len(val) > 80:
                    val = val[:77] + "..."
                detail_str = f" {val}"
                break

    return f"{ts_short} {uid}{role_part} {action}={result}{detail_str}"


def summarize(records: list[dict]) -> dict[str, Any]:
    """Aggregate counts useful for the /logs header."""
    by_action: dict[str, int] = {}
    by_user: dict[str, int] = {}
    by_result: dict[str, int] = {}
    for r in records:
        act = r.get("action", "?")
        by_action[act] = by_action.get(act, 0) + 1
        uid = r.get("user_id") or "—"
        by_user[uid] = by_user.get(uid, 0) + 1
        res = r.get("result", "?")
        by_result[res] = by_result.get(res, 0) + 1
    return {"total": len(records), "by_action": by_action,
            "by_user": by_user, "by_result": by_result}
