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
import sys
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)
import zipfile
import shutil
import tempfile

# Load local modules
sys.path.insert(0, os.path.dirname(__file__))
from ollama_client import OllamaClient
from shell import execute_command
from snapshot import SnapshotManager
from aider_wrapper import AiderWrapper

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/opt/clownfischserver/bot.log"),
    ],
)
logger = logging.getLogger(__name__)

# --- Load env ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))

if not BOT_TOKEN or not CHAT_ID:
    logger.error("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt in .env!")
    sys.exit(1)

# --- Init modules ---
ollama = OllamaClient()
snapshots = SnapshotManager()
aider = AiderWrapper()

# =============================================================================
# AUTH GUARD
# =============================================================================

def is_authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == CHAT_ID

# =============================================================================
# COMMANDS
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🐠 *Clownfischserver online.*\n\n"
        "Schreib mir einfach was du brauchst – ich denke nach und mach's.\n\n"
        "Befehle:\n"
        "• `/snapshots` – alle Snapshots anzeigen\n"
        "• `/rollback <name>` – zu einem Snapshot zurück\n"
        "• `/status` – CPU, RAM, Disk\n"
        "• `/run <befehl>` – direkte Shell, kein Ollama\n"
        "• `/ssh open [ip]` – SSH öffnen\n"
        "• `/ssh close [ip]` – SSH schließen\n"
        "• `/help` – diese Hilfe",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    result = await execute_command("show system status: uptime, memory usage, disk usage, cpu load in a clean summary", ollama, skip_safety=True)
    await update.message.reply_text(f"📊 *Systemstatus*\n\n{result}", parse_mode="Markdown")

async def cmd_snapshots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    snap_list = snapshots.list_snapshots()
    if not snap_list:
        await update.message.reply_text("📸 Keine Snapshots vorhanden.")
        return
    msg = "📸 *Verfügbare Snapshots:*\n\n"
    for s in snap_list[-20:]:  # Show last 20
        msg += f"• `{s}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/rollback <snapshot-name>`\n\nBeispiel: `/rollback 2025-01-15_17-24-00`",
            parse_mode="Markdown"
        )
        return
    snap_name = context.args[0]
    await update.message.reply_text(f"⏪ Rollback zu `{snap_name}` wird eingeleitet...", parse_mode="Markdown")
    result = snapshots.rollback(snap_name)
    await update.message.reply_text(result)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await cmd_start(update, context)

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct shell execution – bypasses Ollama completely"""
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /run <befehl>\n\nBeispiel: /run free -h",
            parse_mode="Markdown"
        )
        return
    cmd = " ".join(context.args)
    await update.message.reply_text(f"⚡ Direkt: `{cmd}`", parse_mode="Markdown")
    stdout, stderr, returncode = await _run_shell_direct(cmd)
    result = stdout or stderr or "✓ Fertig (keine Ausgabe)"
    if len(result) > 4000:
        result = result[:4000] + "\n... (gekürzt)"
    await update.message.reply_text(f"```\n{result}\n```", parse_mode="Markdown")

async def cmd_ssh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open or close SSH via iptables – bypasses Ollama"""
    if not is_authorized(update):
        return
    action = context.args[0].lower() if context.args else ""
    client_ip = context.args[1] if len(context.args) > 1 else None

    if action == "open":
        if client_ip:
            cmds = [
                f"iptables -I INPUT -s {client_ip} -p tcp --dport 22 -j ACCEPT",
                f"echo 'SSH offen für {client_ip} – schließen mit /ssh close {client_ip}'"
            ]
        else:
            cmds = [
                "iptables -I INPUT -p tcp --dport 22 -j ACCEPT",
                "echo 'SSH offen fuer ALLE IPs – schliessen mit /ssh close'"
            ]
        for c in cmds:
            await _run_shell_direct(c)
        ip_info = f"für {client_ip}" if client_ip else "für alle"
        await update.message.reply_text(
            f"🔓 SSH geöffnet {ip_info}!\nVergiss nicht: /ssh close danach!",
            parse_mode="Markdown"
        )

    elif action == "close":
        if client_ip:
            cmd = f"iptables -D INPUT -s {client_ip} -p tcp --dport 22 -j ACCEPT"
        else:
            cmd = "iptables -D INPUT -p tcp --dport 22 -j ACCEPT"
        await _run_shell_direct(cmd)
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

async def _run_shell_direct(command: str):
    """Direct shell execution without Ollama"""
    import asyncio as _asyncio
    process = await _asyncio.create_subprocess_shell(
        command,
        stdout=_asyncio.subprocess.PIPE,
        stderr=_asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
        process.returncode
    )

# =============================================================================
# FILE HANDLER – Self-Update via Telegram
# =============================================================================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads – ZIP = self-update"""
    if not is_authorized(update):
        return

    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or ""

    # Only handle ZIP files
    if not filename.endswith(".zip"):
        await update.message.reply_text(
            f"📎 Datei empfangen: {filename}\nNur .zip Dateien werden als Updates verarbeitet."
        )
        return

    status_msg = await update.message.reply_text(
        f"📦 Update-Paket empfangen: `{filename}`\n"
        "⏳ Verarbeite...",
        parse_mode="Markdown"
    )

    try:
        # Step 1: Snapshot
        await status_msg.edit_text("📸 Erstelle Snapshot vor Update...")
        snap_name = snapshots.create_snapshot(label="pre-update")
        if snap_name:
            await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

        # Step 2: Download ZIP
        await status_msg.edit_text("⬇️ Lade Datei herunter...")
        tmp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, filename)

        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(zip_path)

        # Step 3: Extract
        await status_msg.edit_text("📂 Entpacke ZIP...")
        extract_dir = os.path.join(tmp_dir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        # Find bot/ directory in extracted content
        bot_dir = None
        for root, dirs, files in os.walk(extract_dir):
            if "bot.py" in files:
                bot_dir = root
                break

        if not bot_dir:
            raise FileNotFoundError("Kein bot.py im ZIP gefunden!")

        # Step 4: Copy bot files
        await status_msg.edit_text("📋 Kopiere Bot-Dateien...")
        install_bot_dir = os.path.join(os.getenv("INSTALL_DIR", "/opt/clownfischserver"), "bot")

        for f in os.listdir(bot_dir):
            if f.endswith(".py"):
                src = os.path.join(bot_dir, f)
                dst = os.path.join(install_bot_dir, f)
                shutil.copy2(src, dst)
                os.chmod(dst, 0o644)
                logger.info(f"Updated: {f}")

        # Fix ownership
        import subprocess
        mgmt_user = os.getenv("MGMT_USER", "clownfish")
        subprocess.run(
            ["sudo", "chown", "-R", f"{mgmt_user}:{mgmt_user}", install_bot_dir],
            capture_output=True
        )

        # Cleanup
        shutil.rmtree(tmp_dir, ignore_errors=True)

        await status_msg.edit_text(
            "✅ *Update installiert!*\n\nBot startet in 3 Sekunden neu...",
            parse_mode="Markdown"
        )

        # Step 5: Restart self
        import asyncio
        await asyncio.sleep(3)
        import subprocess
        subprocess.Popen(["sudo", "systemctl", "restart", "clownfisch"])

    except Exception as e:
        logger.error(f"Update fehlgeschlagen: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Update fehlgeschlagen:\n`{e}`\n\nSnapshot zum Rollback verfuegbar.",
            parse_mode="Markdown"
        )

# =============================================================================
# MAIN MESSAGE HANDLER
# =============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        logger.warning(f"Unauthorized access attempt from chat_id: {update.effective_chat.id}")
        return

    user_message = update.message.text
    logger.info(f"Message received: {user_message[:100]}")

    # Thinking indicator
    thinking_msg = await update.message.reply_text("🤔 Analysiere...")

    try:
        # --- Safety check via Ollama ---
        safety = await ollama.safety_check(user_message)

        if safety["dangerous"]:
            await thinking_msg.edit_text(
                f"⚠️ *Verweigert*\n\n{safety['reason']}\n\n"
                f"💡 {safety.get('suggestion', 'Bitte anders formulieren.')}",
                parse_mode="Markdown"
            )
            return

        # --- Take snapshot before action ---
        await thinking_msg.edit_text("📸 Snapshot wird erstellt...")
        snap_name = snapshots.create_snapshot()
        if snap_name:
            await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

        # --- Execute ---
        await thinking_msg.edit_text("⚙️ Wird ausgeführt...")

        if safety.get("type") == "aider":
            result = await aider.run(user_message)
        else:
            result = await execute_command(user_message, ollama)

        # --- Reply (split if too long) ---
        if len(result) > 4000:
            chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
            await thinking_msg.edit_text(f"📤 Ausgabe (Teil 1/{len(chunks)}):\n\n```\n{chunks[0]}\n```", parse_mode="Markdown")
            for i, chunk in enumerate(chunks[1:], 2):
                await update.message.reply_text(f"Teil {i}/{len(chunks)}:\n\n```\n{chunk}\n```", parse_mode="Markdown")
        else:
            await thinking_msg.edit_text(f"✅ Fertig:\n\n```\n{result}\n```", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await thinking_msg.edit_text(
            f"❌ Fehler aufgetreten:\n\n`{str(e)}`\n\n"
            f"Snapshot verfügbar zum Rollback: `{snap_name if 'snap_name' in locals() else 'keiner'}`",
            parse_mode="Markdown"
        )

# =============================================================================
# MAIN
# =============================================================================

def main():
    logger.info("🐠 Clownfischserver Bot startet...")

    # Wait for Ollama with retry loop instead of hard dependency
    logger.info("Warte auf Ollama...")
    import requests as req
    import time
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:2b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    for attempt in range(30):  # max 5 minutes
        try:
            resp = req.post(f"{base_url}/api/chat", json={
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "keep_alive": -1
            }, timeout=30)
            if resp.status_code == 200:
                logger.info("✓ Ollama warm – Bot bereit.")
                break
        except Exception:
            pass
        logger.info(f"Ollama noch nicht bereit – warte... ({attempt+1}/30)")
        time.sleep(10)
    else:
        logger.warning("Ollama nach 5 Minuten nicht bereit – starte trotzdem.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("snapshots", cmd_snapshots))
    app.add_handler(CommandHandler("rollback", cmd_rollback))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("ssh", cmd_ssh))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    logger.info(f"Bot läuft. Authorized Chat-ID: {CHAT_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
