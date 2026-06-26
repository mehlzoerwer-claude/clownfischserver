#!/usr/bin/env python3
"""
🐠 Clownfischserver
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0 – Keep it open. Always.
Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

# Global Ollama ready flag
ollama_ready = None

# Load local modules
sys.path.insert(0, os.path.dirname(__file__))
from ollama_client import OllamaClient
from openrouter_client import OpenRouterClient
from shell import run_shell, execute_command
from snapshot import SnapshotManager, should_snapshot
from aider_wrapper import AiderWrapper
import auth
import audit_log
import audit_query
from llm_router import LLMRouter, OllamaProvider

# --- Load env ---
_install_dir = os.getenv("INSTALL_DIR", "/opt/clownfischserver")
load_dotenv(os.path.join(_install_dir, "config", ".env"))

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(_install_dir, "bot.log")),
    ],
)
logger = logging.getLogger(__name__)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID") or "")

# v0.5.0: auth is satisfied if EITHER legacy TELEGRAM_CHAT_ID OR any of
# the new role envs is set. The bot only requires BOT_TOKEN to boot.
_has_role_config = any(
    os.getenv(k) for k in
    ("CLOWNFISCH_OPERATORS", "CLOWNFISCH_APPROVERS", "CLOWNFISCH_VIEWERS")
)

if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN fehlt in .env!")
    sys.exit(1)
if not CHAT_ID and not _has_role_config:
    logger.error(
        "Weder TELEGRAM_CHAT_ID noch CLOWNFISCH_OPERATORS/APPROVERS/VIEWERS "
        "in .env gesetzt – Bot hätte keine autorisierten Nutzer!"
    )
    sys.exit(1)

# --- Init modules ---
# LLMRouter owns the primary/fallback chain. OpenRouterClient is kept as a
# thin status proxy for backwards-compatible /start banner ("Fallback aktiv").
openrouter = OpenRouterClient()
llm = LLMRouter()
# Legacy alias so any third-party patches/plugins that still refer to `ollama`
# keep working. The router exposes the same async surface.
ollama = llm
snapshots = SnapshotManager()
aider = AiderWrapper()

# =============================================================================
# AUTH GUARD + HELPERS
# =============================================================================

def _user_id(update: Update) -> str | None:
    """Prefer the actual user id over chat id so group chats with multiple
    members still produce distinct audit records."""
    if update.effective_user and update.effective_user.id is not None:
        return str(update.effective_user.id)
    if update.effective_chat:
        return str(update.effective_chat.id)
    return None


def is_authorized(update: Update) -> bool:
    """Backwards-compatible auth check. Delegates to auth.is_authorized()
    which falls back to legacy TELEGRAM_CHAT_ID when no roles are configured."""
    return auth.is_authorized(_user_id(update))


async def deny(update: Update, action: str, required_role: str):
    """Reply with a denial message and write an audit entry."""
    uid = _user_id(update)
    role = auth.get_role(uid)
    audit_log.log_denied(uid, action, role=role,
                         reason=f"requires_{required_role}")
    if update.message:
        try:
            await update.message.reply_text(
                f"⛔ Nicht erlaubt – `{action}` benötigt Rolle `{required_role}`.",
                parse_mode="Markdown",
            )
        except Exception:
            pass


def require(update: Update, *roles: str) -> bool:
    """Returns True if the user holds any of the listed roles.
    Returns False if unauthorized OR role is too weak. Caller must
    short-circuit on False (deny() should be awaited separately)."""
    uid = _user_id(update)
    if not auth.is_authorized(uid):
        return False
    return auth.has_role(uid, *roles)


def sanitize_output(text: str) -> str:
    """Mask sensitive data in bot output: API keys, tokens, passwords, secrets."""
    import re

    # Patterns to mask (key prefix -> replacement)
    patterns = [
        # Bearer tokens (in headers and in text) - MUST come before API key patterns
        (r"Bearer\s+(?:sk-or-v1-[a-zA-Z0-9\-_.]{10,}|sk-[a-zA-Z0-9\-_.]{10,}|[a-zA-Z0-9\-_\.=]{20,})", r"Bearer ***"),
        # Authorization headers
        (r"(Authorization:\s*)[a-zA-Z0-9\-_\.=]{20,}", r"\1***"),
        # OpenRouter keys (full: sk-or-v1-..., display: sk-or-...)
        (r"(sk-or-v1-[a-zA-Z0-9\-_]{10,})", r"sk-or-v1-***"),
        (r"(sk-or-\.{3}[a-zA-Z0-9]{4,})", r"sk-or-***"),
        # Generic API keys (sk-..., pk-...)
        (r"\b(sk-[a-zA-Z0-9\-_]{20,})\b", r"sk-***"),
        (r"\b(pk-[a-zA-Z0-9\-_]{20,})\b", r"pk-***"),
        # Generic long base64-like secrets (32+ chars)
        (r"\b([A-Za-z0-9+/]{32,}={0,2})\b", r"***"),
        # Passwords in URLs
        (r"(://)([^:@/]+):([^:@/]+)@", r"\1\2:***@"),
        # Environment variable assignments with secrets (env-style: VAR=value, VAR: value)
        (r"(?m)^\s*(?:PASSWORD|SECRET|TOKEN|KEY|API_KEY)\s*[=:]?\s*\S+", "***", re.IGNORECASE),
        # Password/passwort in text with assignment (password: value, password=value)
        (r"(?i)(password|passwort|pwd)\s*[:=]\s*\S+", "***"),
        # SSH private key markers
        (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "***PRIVATE KEY***"),
    ]

    result = text
    for pattern_tuple in patterns:
        if len(pattern_tuple) == 3:
            pattern, repl, flags = pattern_tuple
            result = re.sub(pattern, repl, result, flags=flags)
        else:
            pattern, repl = pattern_tuple
            result = re.sub(pattern, repl, result)

    return result


async def safe_reply(target, text: str, parse_mode: str = "Markdown", edit: bool = False):
    """Send or edit a message. Falls back to plain text if Markdown fails."""
    # Sanitize output to prevent leaking secrets
    text = sanitize_output(text)
    try:
        if edit:
            return await target.edit_text(text, parse_mode=parse_mode)
        return await target.reply_text(text, parse_mode=parse_mode)
    except Exception:
        plain = text.replace("`", "").replace("*", "").replace("_", "")
        try:
            if edit:
                return await target.edit_text(plain)
            return await target.reply_text(plain)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

# =============================================================================
# COMMANDS
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_VIEWER):
        await deny(update, "/start", auth.ROLE_VIEWER)
        return

    desc = llm.describe()
    primary_info = ""
    if desc["primary"]:
        primary_info = f"\n🧠 Primary: `{desc['primary']['provider']}` ({desc['primary']['model']})"
    fallback_info = ""
    if desc["fallback"]:
        fallback_info = f"\n🔄 Fallback: `{desc['fallback']['provider']}` ({desc['fallback']['model']})"

    role = auth.get_role(_user_id(update)) or "—"
    audit_log.log_action(_user_id(update), "bot.start", role=role)

    await update.message.reply_text(
        f"🐠 *Clownfischserver v0.5.1 online.*{primary_info}{fallback_info}\n"
        f"👤 Deine Rolle: `{role}`\n\n"
        "Schreib mir einfach – ich antworte als Chat.\n\n"
        "*Befehle:*\n"
        "• `/shell <beschreibung>` – KI generiert Befehl, du bestätigst\n"
        "• `/ja` – letzten Shell-Befehl ausführen\n"
        "• `/code <aufgabe>` – Aider generiert Code\n"
        "• `/run <befehl>` – direkte Shell, kein Ollama\n"
        "• `/status` – CPU, RAM, Disk\n"
        "• `/snapshots` – alle Snapshots anzeigen\n"
        "• `/rollback <n>` – zu einem Snapshot zurück\n"
        "• `/snapshot [label]` – manuell Snapshot erstellen\n"
        "• `/ssh open [ip]` – SSH öffnen\n"
        "• `/ssh close [ip]` – SSH schließen\n"
        "• `/logs [filter]` – Audit-Trail abfragen (operator)\n"
        "• `/help` – diese Hilfe",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_VIEWER):
        await deny(update, "/status", auth.ROLE_VIEWER)
        return
    audit_log.log_action(_user_id(update), "status.read",
                         role=auth.get_role(_user_id(update)))
    cmd = (
        "echo '=== UPTIME ===' && uptime && "
        "echo '=== MEMORY ===' && free -h && "
        "echo '=== DISK ===' && df -h && "
        "echo '=== TOP PROCESSES ===' && ps aux --sort=-%cpu | head -10"
    )
    stdout, stderr, rc = await run_shell(cmd)
    result = stdout or stderr or "Keine Ausgabe"
    if len(result) > 4000:
        result = result[:4000] + "\n... (gekürzt)"
    await safe_reply(update.message, f"📊 Systemstatus\n\n```\n{result}\n```")

async def cmd_snapshots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_VIEWER):
        await deny(update, "/snapshots", auth.ROLE_VIEWER)
        return
    audit_log.log_action(_user_id(update), "snapshots.list",
                         role=auth.get_role(_user_id(update)))
    snap_list = snapshots.list_snapshots()
    if not snap_list:
        await update.message.reply_text("📸 Keine Snapshots vorhanden.")
        return
    msg = "📸 *Snapshots:*\n\n"
    for s in snap_list[:20]:
        star = "⭐ " if s["kept"] else ""
        msg += f"• {star}`{s['name']}` ({s['size_mb']}MB)\n"
    msg += f"\n_Gesamt: {len(snap_list)} | Max auto: 20 (⭐ bleiben immer)_\n"
    msg += "\n`/snapshot keep <n>` – wichtig markieren\n"
    msg += "`/snapshot delete <n>` – löschen"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "/rollback", auth.ROLE_OPERATOR)
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/rollback <snapshot-name>`\n\nBeispiel: `/rollback 2025-01-15_17-24-00`",
            parse_mode="Markdown"
        )
        return
    snap_name = context.args[0]
    audit_log.log_action(
        _user_id(update), "snapshot.rollback",
        role=auth.get_role(_user_id(update)),
        details={"snapshot": snap_name},
    )
    await update.message.reply_text(f"⏪ Rollback zu `{snap_name}` wird eingeleitet...", parse_mode="Markdown")
    result = snapshots.rollback(snap_name)
    await update.message.reply_text(result)

async def cmd_snapshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Snapshot management: create, keep, delete"""
    args = context.args
    subcmd = args[0].lower() if args else "create"

    # Read-only subcommands are viewer-accessible; everything else mutates
    # and requires operator.
    if subcmd in ("list", "ls"):
        required = auth.ROLE_VIEWER
    else:
        required = auth.ROLE_OPERATOR

    if not require(update, required):
        await deny(update, f"/snapshot {subcmd}", required)
        return

    audit_log.log_action(
        _user_id(update), f"snapshot.{subcmd}",
        role=auth.get_role(_user_id(update)),
        details={"args": args[1:] if len(args) > 1 else []},
    )

    if subcmd == "keep" and len(args) > 1:
        result = snapshots.keep_snapshot(args[1])
        await update.message.reply_text(result)
    elif subcmd == "unkeep" and len(args) > 1:
        result = snapshots.unkeep_snapshot(args[1])
        await update.message.reply_text(result)
    elif subcmd == "delete" and len(args) > 1:
        result = snapshots.delete_snapshot(args[1])
        await update.message.reply_text(result)
    elif subcmd in ("list", "ls"):
        await cmd_snapshots(update, context)
    else:
        label = args[0] if args and subcmd not in ("create",) else "manual"
        if subcmd == "create":
            label = args[1] if len(args) > 1 else "manual"
        await update.message.reply_text(f"📸 Erstelle Snapshot ({label})...")
        snap_name = snapshots.create_snapshot(label=label)
        if snap_name:
            await update.message.reply_text(
                f"✅ Snapshot erstellt: `{snap_name}`\n\nAls wichtig markieren: `/snapshot keep {snap_name}`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Snapshot fehlgeschlagen – check Logs.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_VIEWER):
        await deny(update, "/help", auth.ROLE_VIEWER)
        return
    await cmd_start(update, context)

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Operator-only audit query.

    Usage:
      /logs                          → last 20 entries
      /logs user 12345               → filter by user
      /logs action shell.execute     → exact action
      /logs prefix shell.            → action prefix
      /logs days 7                   → last 7 days only
      /logs result denied            → filter by result
      /logs limit 50                 → up to 50 entries
      Filters can be combined: /logs user 12345 days 1 limit 10
    """
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "/logs", auth.ROLE_OPERATOR)
        return

    args = list(context.args) if context.args else []
    filters: dict[str, object] = {"limit": 20}
    i = 0
    while i < len(args) - 1:
        key = args[i].lower()
        val = args[i + 1]
        if key == "user":
            filters["user_id"] = val
        elif key == "action":
            filters["action"] = val
        elif key == "prefix":
            filters["action_prefix"] = val
        elif key == "result":
            filters["result"] = val
        elif key == "days":
            try:
                filters["days"] = int(val)
            except ValueError:
                await update.message.reply_text(f"❌ `days` muss eine Zahl sein, war `{val}`",
                                                parse_mode="Markdown")
                return
        elif key == "limit":
            try:
                filters["limit"] = max(1, min(200, int(val)))
            except ValueError:
                await update.message.reply_text(f"❌ `limit` muss eine Zahl sein, war `{val}`",
                                                parse_mode="Markdown")
                return
        else:
            await update.message.reply_text(
                f"❓ Unbekannter Filter `{key}`. Erlaubt: user, action, prefix, result, days, limit",
                parse_mode="Markdown")
            return
        i += 2

    audit_log.log_action(
        _user_id(update), "logs.query",
        role=auth.get_role(_user_id(update)),
        details={"filters": filters},
    )

    try:
        records = audit_query.query(**filters)
    except Exception as e:
        logger.error(f"audit query failed: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Audit-Query fehlgeschlagen: `{e}`",
                                        parse_mode="Markdown")
        return

    if not records:
        await update.message.reply_text("📭 Keine passenden Audit-Einträge.")
        return

    summary = audit_query.summarize(records)
    header = f"📜 *{summary['total']} Einträge*"
    if summary["by_result"]:
        header += " · " + ", ".join(
            f"{k}={v}" for k, v in sorted(summary["by_result"].items())
        )

    lines = [audit_query.format_record(r) for r in records]
    body = "\n".join(lines)
    # Telegram limit ~4096; chunk if necessary.
    msg = f"{header}\n```\n{body}\n```"
    if len(msg) > 4000:
        # Drop the code-fence wrapping for large results and split.
        await safe_reply(update.message, header)
        chunk_size = 3800
        for i in range(0, len(body), chunk_size):
            chunk = body[i:i + chunk_size]
            await safe_reply(update.message, f"```\n{chunk}\n```")
    else:
        await safe_reply(update.message, msg)

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct shell execution – bypasses Ollama completely"""
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "/run", auth.ROLE_OPERATOR)
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /run <befehl>\n\nBeispiel: /run free -h",
            parse_mode="Markdown"
        )
        return
    cmd = " ".join(context.args)
    uid = _user_id(update)
    role = auth.get_role(uid)
    await update.message.reply_text(f"⚡ Direkt: `{cmd}`", parse_mode="Markdown")
    stdout, stderr, returncode = await run_shell(cmd)
    audit_log.log_shell(uid, cmd, role=role,
                        status="ok" if returncode == 0 else "error",
                        returncode=returncode, stderr=stderr or None)
    result = stdout or stderr or "✓ Fertig (keine Ausgabe)"
    if len(result) > 4000:
        result = result[:4000] + "\n... (gekürzt)"
    await safe_reply(update.message, f"```\n{result}\n```")

async def cmd_ssh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open or close SSH via ufw"""
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "/ssh", auth.ROLE_OPERATOR)
        return
    action = context.args[0].lower() if context.args else ""
    client_ip = context.args[1] if len(context.args) > 1 else None
    audit_log.log_action(
        _user_id(update), "ssh.toggle",
        role=auth.get_role(_user_id(update)),
        details={"action": action, "client_ip": client_ip},
    )

    if action == "open":
        if client_ip:
            await run_shell(f"sudo ufw allow from {client_ip} to any port 22 comment 'clownfisch-ssh'")
        else:
            await run_shell("sudo ufw allow 22/tcp comment 'clownfisch-ssh'")
        ip_info = f"für {client_ip}" if client_ip else "für alle"
        await update.message.reply_text(
            f"🔓 SSH geöffnet {ip_info}!\nVergiss nicht: /ssh close danach!",
            parse_mode="Markdown"
        )
    elif action == "close":
        if client_ip:
            await run_shell(f"sudo ufw delete allow from {client_ip} to any port 22")
        else:
            await run_shell("sudo ufw delete allow 22/tcp")
        await update.message.reply_text("🔒 SSH wieder geschlossen.")
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/ssh open – SSH für alle öffnen\n"
            "/ssh open 1.2.3.4 – SSH nur für deine IP\n"
            "/ssh close – SSH schließen\n"
            "/ssh close 1.2.3.4 – SSH für IP schließen",
            parse_mode="Markdown"
        )

# =============================================================================
# /shell – KI generiert Befehl, Nutzer bestätigt mit /ja
# =============================================================================

async def cmd_shell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "/shell", auth.ROLE_OPERATOR)
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/shell <was du tun willst>`\n\n"
            "Beispiel: `/shell zeig mir den freien RAM`",
            parse_mode="Markdown"
        )
        return

    primary_is_ollama = isinstance(llm.primary, OllamaProvider)
    ollama_warming = ollama_ready is None or not ollama_ready.is_set()
    if primary_is_ollama and ollama_warming and not llm.has_fallback():
        await update.message.reply_text("⏳ Ollama lädt noch – bitte kurz warten.")
        return

    description = " ".join(context.args)
    thinking_msg = await update.message.reply_text("🤔 Generiere Befehl...")

    try:
        result = await ollama.generate_shell_command(description)
        command = result.get("command", "").strip()
        error = result.get("_error", "")

        if error:
            await safe_reply(thinking_msg, f"⚠️ {error}", edit=True)
            return

        if not command:
            await safe_reply(thinking_msg, "❌ Konnte keinen Befehl generieren. Versuch es anders zu formulieren.", edit=True)
            return

        uid = _user_id(update)
        role = auth.get_role(uid)

        if result.get("dangerous", False):
            audit_log.log_shell_proposed(uid, description, command,
                                         role=role, dangerous=True)
            await safe_reply(thinking_msg,
                f"⚠️ *Gefährlicher Befehl verweigert!*\n\n"
                f"Befehl: `{command}`\n"
                f"Grund: {result.get('reason', 'Zu riskant')}",
                edit=True
            )
            return

        audit_log.log_shell_proposed(uid, description, command, role=role)
        context.user_data["pending_cmd"] = command
        await safe_reply(thinking_msg,
            f"🔧 Vorgeschlagener Befehl:\n\n"
            f"`{command}`\n\n"
            f"→ Mit `/ja` ausführen oder einfach ignorieren.",
            edit=True
        )
    except Exception as e:
        logger.error(f"cmd_shell failed: {e}", exc_info=True)
        await safe_reply(thinking_msg, f"❌ Fehler: `{e}`", edit=True)

# =============================================================================
# /ja – Bestätigung für pending /shell Befehl
# =============================================================================

async def cmd_ja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /ja is the approval gate – approver inherits to operator.
    if not require(update, auth.ROLE_APPROVER):
        await deny(update, "/ja", auth.ROLE_APPROVER)
        return

    pending = context.user_data.get("pending_cmd")
    if not pending:
        await update.message.reply_text("❓ Kein ausstehender Befehl. Nutze erst `/shell <beschreibung>`.", parse_mode="Markdown")
        return

    command = pending
    context.user_data.pop("pending_cmd", None)
    uid = _user_id(update)
    role = auth.get_role(uid)
    audit_log.log_approval(uid, command, role=role, approved=True)

    snap_name = None
    if should_snapshot(command):
        await update.message.reply_text("📸 Snapshot wird erstellt...")
        snap_name = snapshots.create_snapshot()
        if snap_name:
            await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

    status_msg = await update.message.reply_text(f"⚙️ Ausführung: `{command}`", parse_mode="Markdown")

    try:
        result = await execute_command(command, ollama)
        audit_log.log_shell(uid, command, role=role, status="ok")
        if len(result) > 4000:
            chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
            await safe_reply(status_msg, f"✅ Ergebnis (Teil 1/{len(chunks)}):\n\n```\n{chunks[0]}\n```", edit=True)
            for i, chunk in enumerate(chunks[1:], 2):
                await safe_reply(update.message, f"Teil {i}/{len(chunks)}:\n\n```\n{chunk}\n```")
        else:
            await safe_reply(status_msg, f"✅ Ergebnis:\n\n```\n{result}\n```", edit=True)
    except Exception as e:
        logger.error(f"cmd_ja execution failed: {e}", exc_info=True)
        audit_log.log_shell(uid, command, role=role, status="error",
                            stderr=str(e))
        await safe_reply(status_msg,
            f"❌ Fehler:\n`{e}`\n\nSnapshot: `{snap_name or 'keiner'}`",
            edit=True
        )

# =============================================================================
# /code – Aider für Code-Generierung
# =============================================================================

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "/code", auth.ROLE_OPERATOR)
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/code <aufgabe>`\n\n"
            "Beispiel: `/code erstelle eine einfache Flask API`\n\n"
            "💡 Tipp: Kläre Details erst im Chat, dann `/code` mit klarer Aufgabe.",
            parse_mode="Markdown"
        )
        return

    task = " ".join(context.args)

    # Smart prompt: ensure Aider creates a FILE, not just chat output
    workspace = os.getenv("AIDER_WORKDIR", "/opt/clownfisch-workspace")
    task_lower = task.lower()

    # Only auto-generate a filepath if the task doesn't already point at one.
    words = task.split()
    first_word_is_path = bool(words) and "/" in words[0]
    needs_filepath = (
        workspace not in task
        and "/opt/" not in task
        and not first_word_is_path
    )

    if needs_filepath:
        file_match = re.search(r'(\S+\.(sh|py|js|ts|html|css|yaml|yml|json|conf|cfg|txt))', task)
        if file_match:
            filename = file_match.group(1)
            filepath = f"{workspace}/{filename}"
        else:
            words = re.sub(r'[^a-z0-9 ]', '', task_lower).split()[:3]
            slug = "-".join(words) if words else "script"
            ext = ".py" if "python" in task_lower else ".sh"
            filepath = f"{workspace}/{slug}{ext}"

        task = f"erstelle die datei {filepath} mit folgendem inhalt: {task}"
        logger.info(f"Code task enhanced: {task[:100]}")

    status_msg = await update.message.reply_text("🛠️ Aider arbeitet...")

    snap_name = snapshots.create_snapshot(label="pre-aider")
    if snap_name:
        await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

    uid = _user_id(update)
    role = auth.get_role(uid)

    try:
        result = await aider.run(task)
        audit_log.log_code(uid, task, role=role, status="ok")
        if len(result) > 4000:
            result = result[:4000] + "\n... (gekürzt)"
        await safe_reply(status_msg, f"🛠️ Aider Ergebnis:\n\n```\n{result}\n```", edit=True)
    except Exception as e:
        logger.error(f"cmd_code failed: {e}", exc_info=True)
        audit_log.log_code(uid, task, role=role, status="error")
        await safe_reply(status_msg,
            f"❌ Aider Fehler:\n`{e}`\n\nSnapshot: `{snap_name or 'keiner'}`",
            edit=True
        )

# =============================================================================
# FILE HANDLER – Self-Update via Telegram
# =============================================================================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads – ZIP = self-update"""
    if not require(update, auth.ROLE_OPERATOR):
        await deny(update, "file.upload", auth.ROLE_OPERATOR)
        return

    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or ""

    if not filename.endswith(".zip"):
        await update.message.reply_text(
            f"📎 Datei empfangen: {filename}\nNur .zip Dateien werden als Updates verarbeitet."
        )
        return

    status_msg = await update.message.reply_text(
        f"📦 Update-Paket empfangen: `{filename}`\n⏳ Verarbeite...",
        parse_mode="Markdown"
    )

    try:
        # Snapshot before update
        await status_msg.edit_text("📸 Erstelle Snapshot vor Update...")
        snap_name = snapshots.create_snapshot(label="pre-update")
        if snap_name:
            await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

        # Download ZIP
        await status_msg.edit_text("⬇️ Lade Datei herunter...")
        tmp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, filename)
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(zip_path)

        # Extract
        # PowerShell's Compress-Archive writes path entries with backslashes,
        # which Python's zipfile does NOT split on under POSIX – without this
        # normalization the archive extracts as flat files named
        # "clownfischserver\bot\bot.py", and os.walk never finds bot.py.
        await status_msg.edit_text("📂 Entpacke ZIP...")
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            for info in z.infolist():
                normalized = info.filename.replace("\\", "/")
                if not normalized or normalized.endswith("/"):
                    if normalized:
                        os.makedirs(os.path.join(extract_dir, normalized.rstrip("/")),
                                    exist_ok=True)
                    continue
                target_path = os.path.join(extract_dir, *normalized.split("/"))
                # Zip-Slip guard: refuse entries that escape extract_dir.
                if not os.path.abspath(target_path).startswith(
                        os.path.abspath(extract_dir) + os.sep):
                    raise ValueError(f"Unsicherer Pfad im ZIP: {info.filename}")
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with z.open(info) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        # Find bot/ directory
        bot_dir = None
        for root, dirs, files in os.walk(extract_dir):
            if "bot.py" in files:
                bot_dir = root
                break

        if not bot_dir:
            raise FileNotFoundError("Kein bot.py im ZIP gefunden!")

        # Check if openrouter_client.py is in the update
        has_openrouter = os.path.exists(os.path.join(bot_dir, "openrouter_client.py"))

        if has_openrouter and not openrouter.is_available():
            # New feature available – ask user if they want to set it up
            context.user_data["update_tmp_dir"] = tmp_dir
            context.user_data["update_bot_dir"] = bot_dir
            context.user_data["update_extract_dir"] = extract_dir
            context.user_data["update_step"] = "ask_openrouter"

            await status_msg.edit_text(
                "✅ Update-Paket gültig\n\n"
                "🆕 *Neues Feature: OpenRouter Fallback*\n\n"
                "Wenn Ollama mal zu langsam ist, kann der Bot\n"
                "kostenlose Cloud-Modelle als Backup nutzen.\n"
                "Kein Zwang, keine Kreditkarte nötig.\n\n"
                "Möchtest du OpenRouter aktivieren?\n"
                "Antworte: `ja` oder `nein`",
                parse_mode="Markdown"
            )
        else:
            # No OpenRouter setup needed – install directly
            await _perform_update(update, context, tmp_dir, bot_dir, extract_dir)

    except Exception as e:
        logger.error(f"Update fehlgeschlagen: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Update fehlgeschlagen:\n`{e}`\n\nSnapshot zum Rollback verfügbar.",
            parse_mode="Markdown"
        )


async def _perform_update(update, context, tmp_dir, bot_dir, extract_dir, openrouter_key=None):
    """Execute the actual update installation."""
    try:
        msg = await update.message.reply_text("📋 Kopiere Bot-Dateien...")
        install_dir = os.getenv("INSTALL_DIR", "/opt/clownfischserver")
        install_bot_dir = os.path.join(install_dir, "bot")
        mgmt_user = os.getenv("MGMT_USER", "clownfish")

        for f in os.listdir(bot_dir):
            if f.endswith(".py"):
                src = os.path.join(bot_dir, f)
                dst = os.path.join(install_bot_dir, f)
                shutil.copy2(src, dst)
                os.chmod(dst, 0o644)
                logger.info(f"Updated: {f}")

        subprocess.run(
            ["sudo", "chown", "-R", f"{mgmt_user}:{mgmt_user}", install_bot_dir],
            capture_output=True,
        )

        # Copy systemd services – patch User= with actual MGMT_USER
        systemd_dir = None
        for root, dirs, files in os.walk(extract_dir):
            if any(f.endswith(".service") for f in files):
                systemd_dir = root
                break

        if systemd_dir:
            for f in os.listdir(systemd_dir):
                if f.endswith(".service"):
                    src = os.path.join(systemd_dir, f)
                    with open(src, "r") as sf:
                        service_content = sf.read()
                    # Replace ANY User=/Group= value with actual MGMT_USER
                    service_content = re.sub(r'User=\S+', f'User={mgmt_user}', service_content)
                    service_content = re.sub(r'Group=\S+', f'Group={mgmt_user}', service_content)
                    tmp_svc = os.path.join(install_dir, f".tmp_{f}")
                    with open(tmp_svc, "w") as sf:
                        sf.write(service_content)
                    subprocess.run(["sudo", "cp", tmp_svc, f"/etc/systemd/system/{f}"], capture_output=True)
                    os.remove(tmp_svc)
                    logger.info(f"Service updated: {f} (User={mgmt_user})")
            subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
            subprocess.run(["sudo", "systemctl", "enable", "clownfisch-boot"], capture_output=True)

        # Save OpenRouter key if provided
        if openrouter_key:
            env_file = os.path.join(install_dir, "config", ".env")
            try:
                with open(env_file, "r") as f:
                    env_content = f.read()
            except FileNotFoundError:
                env_content = ""

            if "OPENROUTER_API_KEY=" in env_content:
                env_content = re.sub(r'OPENROUTER_API_KEY=.*', f'OPENROUTER_API_KEY={openrouter_key}', env_content)
            else:
                env_content += f"\nOPENROUTER_API_KEY={openrouter_key}\n"

            with open(env_file, "w") as f:
                f.write(env_content)
            os.chmod(env_file, 0o600)
            logger.info("OpenRouter Key in .env gespeichert")

        # Cleanup
        shutil.rmtree(tmp_dir, ignore_errors=True)

        # Clear update state
        for key in ["update_tmp_dir", "update_bot_dir", "update_extract_dir", "update_step", "update_openrouter_key"]:
            context.user_data.pop(key, None)

        or_status = "\n✅ OpenRouter Fallback aktiviert" if openrouter_key else ""
        await msg.edit_text(
            f"✅ *Update installiert!*{or_status}\n\nBot startet in 3 Sekunden neu...",
            parse_mode="Markdown"
        )

        await asyncio.sleep(3)
        subprocess.Popen(["sudo", "systemctl", "restart", "clownfisch"])

    except Exception as e:
        logger.error(f"Update execution failed: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Update fehlgeschlagen:\n`{e}`\n\nSnapshot zum Rollback verfügbar.",
            parse_mode="Markdown"
        )
        for key in ["update_tmp_dir", "update_bot_dir", "update_extract_dir", "update_step"]:
            context.user_data.pop(key, None)

# =============================================================================
# MAIN MESSAGE HANDLER – Chat + Update Dialog
# =============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Normal messages: either handle update dialog or go to Ollama chat."""
    uid = _user_id(update)
    if not require(update, auth.ROLE_VIEWER):
        logger.warning(f"Unauthorized access attempt from user_id: {uid}")
        audit_log.log_denied(uid, "chat.message", reason="unauthorized")
        return

    user_message = update.message.text.strip()

    # --- Active update dialog? Handle that first, don't send to chat ---
    update_step = context.user_data.get("update_step")
    if update_step:
        await _handle_update_dialog(update, context, user_message, update_step)
        return

    # --- Normal chat ---
    logger.info(f"Chat message: {user_message[:100]}")

    primary_is_ollama = isinstance(llm.primary, OllamaProvider)
    ollama_warming = ollama_ready is None or not ollama_ready.is_set()
    if primary_is_ollama and ollama_warming and not llm.has_fallback():
        await update.message.reply_text(
            "⏳ Ollama lädt noch...\n\n"
            "Direkte Befehle funktionieren sofort:\n"
            "• /run <befehl>\n"
            "• /ssh open/close\n"
            "• /status\n\n"
            "Bitte in ~1 Minute nochmal versuchen."
        )
        return

    thinking_msg = await update.message.reply_text("💬 ...")

    try:
        history = context.user_data.get("chat_history", [])
        result = await ollama.chat(user_message, history=history)

        # Sanitize LLM response before sending
        result = sanitize_output(result)

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": result})
        if len(history) > 20:
            history = history[-20:]
        context.user_data["chat_history"] = history

        if len(result) > 4000:
            chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
            await thinking_msg.edit_text(f"💬 {chunks[0]}")
            for i, chunk in enumerate(chunks[1:], 2):
                await update.message.reply_text(f"💬 ({i}/{len(chunks)}) {chunk}")
        else:
            await thinking_msg.edit_text(f"💬 {result}")

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        error_msg = sanitize_output(f"❌ Chat-Fehler: `{e}`")
        await thinking_msg.edit_text(error_msg, parse_mode="Markdown")


async def _handle_update_dialog(update, context, user_input, step):
    """Handle interactive update setup dialog (OpenRouter key etc.)."""
    user_input_lower = user_input.lower()

    if step == "ask_openrouter":
        if user_input_lower in ("ja", "yes", "j", "y"):
            context.user_data["update_step"] = "ask_openrouter_key"
            await update.message.reply_text(
                "🔑 *OpenRouter API Key eingeben*\n\n"
                "Kostenlos – keine Kreditkarte nötig!\n\n"
                "1. Gehe zu openrouter.ai\n"
                "2. Sign up (2 Minuten)\n"
                "3. Settings → API Keys\n"
                "4. Key kopieren und hier senden\n\n"
                "Format: `sk-or-v1-...`",
                parse_mode="Markdown"
            )
        elif user_input_lower in ("nein", "no", "n"):
            tmp_dir = context.user_data.get("update_tmp_dir")
            bot_dir = context.user_data.get("update_bot_dir")
            extract_dir = context.user_data.get("update_extract_dir")
            await _perform_update(update, context, tmp_dir, bot_dir, extract_dir)
        else:
            await update.message.reply_text("❓ Bitte antworte mit `ja` oder `nein`", parse_mode="Markdown")

    elif step == "ask_openrouter_key":
        key = user_input.strip()
        if len(key) < 20:
            await update.message.reply_text(
                "❌ Key zu kurz. Bitte den kompletten Key von openrouter.ai senden.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text("✅ Key gespeichert – Installation startet...")
        tmp_dir = context.user_data.get("update_tmp_dir")
        bot_dir = context.user_data.get("update_bot_dir")
        extract_dir = context.user_data.get("update_extract_dir")
        await _perform_update(update, context, tmp_dir, bot_dir, extract_dir, openrouter_key=key)

# =============================================================================
# MAIN
# =============================================================================

def main():
    logger.info("🐠 Clownfischserver v0.5.1 Bot startet...")

    import requests as req
    import time
    import threading

    # Pull Ollama models from the router – respects LLM_*_MODEL overrides
    # and falls back to OLLAMA_MODEL/OLLAMA_MODEL_FAST for backwards compat.
    base_url = llm.ollama_base_url
    ollama_models = llm.ollama_models

    global ollama_ready
    ollama_ready = threading.Event()

    def warmup_model(model_name, label):
        for attempt in range(60):
            try:
                resp = req.post(f"{base_url}/api/chat", json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "keep_alive": -1,
                }, timeout=150)
                if resp.status_code == 200:
                    logger.info(f"✓ {label} warm: {model_name}")
                    return True
            except Exception:
                pass
            time.sleep(3)
        logger.warning(f"{label} nach 3 Minuten nicht bereit: {model_name}")
        return False

    def warmup_ollama():
        if not ollama_models:
            logger.info("Kein Ollama-Provider konfiguriert – Warmup übersprungen.")
            ollama_ready.set()
            return
        logger.info(f"Ollama Warmup gestartet (Hintergrund): {ollama_models}")
        for idx, m in enumerate(ollama_models):
            label = "Fast-Modell" if idx == 0 and len(ollama_models) > 1 else "Hauptmodell"
            warmup_model(m, label)
        ollama_ready.set()

    threading.Thread(target=warmup_ollama, daemon=True).start()
    if ollama_models:
        logger.info(f"🐠 Bot startet – Ollama warmup für {len(ollama_models)} Modell(e)")
    else:
        logger.info("🐠 Bot startet – kein Ollama-Provider, kein Warmup")
        ollama_ready.set()

    route_desc = llm.describe()
    logger.info(f"LLM Routing: {route_desc}")

    # Audit-Trail Setup: prune old logs on boot, log the role roster.
    dropped = audit_log.prune_old_logs()
    if dropped:
        logger.info(f"Audit: {dropped} alte Einträge entfernt (Retention)")
    roster = auth.describe_roles()
    logger.info(
        f"Rollen: operators={len(roster['operator'])} "
        f"approvers={len(roster['approver'])} viewers={len(roster['viewer'])}"
    )
    audit_log.log_action(None, "bot.boot", details={"roster": roster})

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("snapshots", cmd_snapshots))
    app.add_handler(CommandHandler("rollback", cmd_rollback))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("snapshot", cmd_snapshot))
    app.add_handler(CommandHandler("ssh", cmd_ssh))
    app.add_handler(CommandHandler("shell", cmd_shell))
    app.add_handler(CommandHandler("ja", cmd_ja))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("logs", cmd_logs))

    # Messages – single handler for chat AND update dialog (no double-processing)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    legacy_info = f" legacy_chat={CHAT_ID}" if CHAT_ID else ""
    logger.info(f"Bot läuft. Rollen geladen.{legacy_info}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(app.initialize())
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        loop.run_until_complete(app.shutdown())

if __name__ == "__main__":
    main()
