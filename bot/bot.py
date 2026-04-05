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
from shell import run_shell, execute_command
from snapshot import SnapshotManager, should_snapshot
from aider_wrapper import AiderWrapper

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
# SAFE TELEGRAM HELPER
# =============================================================================

async def safe_reply(target, text: str, parse_mode: str = "Markdown", edit: bool = False):
    """Send or edit a message. Falls back to plain text if Markdown fails."""
    try:
        if edit:
            return await target.edit_text(text, parse_mode=parse_mode)
        return await target.reply_text(text, parse_mode=parse_mode)
    except Exception:
        # Strip markdown and retry as plain text
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
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🐠 *Clownfischserver v0.4.11 online.*\n\n"
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
        "• `/help` – diese Hilfe",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
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
    if not is_authorized(update):
        return
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

async def cmd_snapshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Snapshot management: create, keep, delete"""
    if not is_authorized(update):
        return

    args = context.args
    subcmd = args[0].lower() if args else "create"

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
        # Create snapshot with optional label
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
    stdout, stderr, returncode = await run_shell(cmd)
    result = stdout or stderr or "✓ Fertig (keine Ausgabe)"
    if len(result) > 4000:
        result = result[:4000] + "\n... (gekürzt)"
    await safe_reply(update.message, f"```\n{result}\n```")

async def cmd_ssh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open or close SSH via iptables – bypasses Ollama"""
    if not is_authorized(update):
        return
    action = context.args[0].lower() if context.args else ""
    client_ip = context.args[1] if len(context.args) > 1 else None

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
    """Generate a shell command from natural language, show for confirmation."""
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/shell <was du tun willst>`\n\n"
            "Beispiel: `/shell zeig mir den freien RAM`\n"
            "Beispiel: `/shell installiere nginx`",
            parse_mode="Markdown"
        )
        return

    if ollama_ready is None or not ollama_ready.is_set():
        await update.message.reply_text("⏳ Ollama lädt noch – bitte kurz warten.")
        return

    description = " ".join(context.args)
    thinking_msg = await update.message.reply_text("🤔 Generiere Befehl...")

    try:
        result = await ollama.generate_shell_command(description)
        command = result.get("command", "").strip()

        if not command:
            await thinking_msg.edit_text("❌ Konnte keinen Befehl generieren. Versuch es anders zu formulieren.")
            return

        if result.get("dangerous", False):
            await thinking_msg.edit_text(
                f"⚠️ *Gefährlicher Befehl verweigert!*\n\n"
                f"Befehl: `{command}`\n"
                f"Grund: {result.get('reason', 'Zu riskant')}",
                parse_mode="Markdown"
            )
            return

        # Store pending command for /ja confirmation
        context.user_data["pending_cmd"] = command
        context.user_data["pending_desc"] = description

        await thinking_msg.edit_text(
            f"🔧 Vorgeschlagener Befehl:\n\n"
            f"`{command}`\n\n"
            f"→ Mit `/ja` ausführen oder einfach ignorieren.",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"cmd_shell failed: {e}", exc_info=True)
        await thinking_msg.edit_text(f"❌ Fehler: `{e}`", parse_mode="Markdown")

# =============================================================================
# /ja – Bestätigung für pending /shell Befehl
# =============================================================================

async def cmd_ja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the pending shell command from /shell."""
    if not is_authorized(update):
        return

    pending = context.user_data.get("pending_cmd")
    if not pending:
        await update.message.reply_text("❓ Kein ausstehender Befehl. Nutze erst `/shell <beschreibung>`.", parse_mode="Markdown")
        return

    command = pending
    context.user_data.pop("pending_cmd", None)
    context.user_data.pop("pending_desc", None)

    # Snapshot before destructive commands
    snap_name = None
    if should_snapshot(command):
        await update.message.reply_text("📸 Snapshot wird erstellt...")
        snap_name = snapshots.create_snapshot()
        if snap_name:
            await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

    status_msg = await update.message.reply_text(f"⚙️ Ausführung: `{command}`", parse_mode="Markdown")

    try:
        result = await execute_command(command, ollama)

        if len(result) > 4000:
            chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
            await safe_reply(status_msg, f"✅ Ergebnis (Teil 1/{len(chunks)}):\n\n```\n{chunks[0]}\n```", edit=True)
            for i, chunk in enumerate(chunks[1:], 2):
                await safe_reply(update.message, f"Teil {i}/{len(chunks)}:\n\n```\n{chunk}\n```")
        else:
            await safe_reply(status_msg, f"✅ Ergebnis:\n\n```\n{result}\n```", edit=True)

    except Exception as e:
        logger.error(f"cmd_ja execution failed: {e}", exc_info=True)
        await safe_reply(status_msg,
            f"❌ Fehler:\n`{e}`\n\n"
            f"Snapshot: `{snap_name or 'keiner'}`",
            edit=True
        )

# =============================================================================
# /code – Aider für Code-Generierung
# =============================================================================

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send task to Aider for autonomous code generation."""
    if not is_authorized(update):
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
    status_msg = await update.message.reply_text("🛠️ Aider arbeitet...")

    # Snapshot before code changes
    snap_name = snapshots.create_snapshot(label="pre-aider")
    if snap_name:
        await update.message.reply_text(f"📸 Snapshot: `{snap_name}`", parse_mode="Markdown")

    try:
        result = await aider.run(task)
        if len(result) > 4000:
            result = result[:4000] + "\n... (gekürzt)"
        await safe_reply(status_msg, f"🛠️ Aider Ergebnis:\n\n```\n{result}\n```", edit=True)
    except Exception as e:
        logger.error(f"cmd_code failed: {e}", exc_info=True)
        await safe_reply(status_msg,
            f"❌ Aider Fehler:\n`{e}`\n\n"
            f"Snapshot: `{snap_name or 'keiner'}`",
            edit=True
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
        await asyncio.sleep(3)
        subprocess.Popen(["sudo", "systemctl", "restart", "clownfisch"])

    except Exception as e:
        logger.error(f"Update fehlgeschlagen: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Update fehlgeschlagen:\n`{e}`\n\nSnapshot zum Rollback verfuegbar.",
            parse_mode="Markdown"
        )

# =============================================================================
# MAIN MESSAGE HANDLER – Direct Chat (no classifier)
# =============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Normal messages go straight to Ollama chat – no classification."""
    if not is_authorized(update):
        logger.warning(f"Unauthorized access attempt from chat_id: {update.effective_chat.id}")
        return

    user_message = update.message.text
    logger.info(f"Chat message: {user_message[:100]}")

    if ollama_ready is None or not ollama_ready.is_set():
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
        # Build chat history from user_data
        history = context.user_data.get("chat_history", [])
        result = await ollama.chat(user_message, history=history)

        # Save last few exchanges for context
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": result})
        # Keep last 10 exchanges (20 messages)
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
        await thinking_msg.edit_text(f"❌ Chat-Fehler: `{e}`", parse_mode="Markdown")

# =============================================================================
# MAIN
# =============================================================================

def main():
    logger.info("🐠 Clownfischserver v0.4.11 Bot startet...")

    # Start bot immediately – warm up Ollama in background
    import requests as req
    import time
    import threading

    model = os.getenv("OLLAMA_MODEL", "qwen2.5:2b")
    model_fast = os.getenv("OLLAMA_MODEL_FAST", "")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Global flag – commands that need Ollama check this
    global ollama_ready
    ollama_ready = threading.Event()

    def warmup_model(model_name, label):
        """Warm up a single model."""
        for attempt in range(60):
            try:
                resp = req.post(f"{base_url}/api/chat", json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "keep_alive": -1
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
        logger.info("Ollama Warmup gestartet (Hintergrund)...")
        models_to_warm = [(model, "Hauptmodell")]
        if model_fast and model_fast != model:
            models_to_warm.insert(0, (model_fast, "Fast-Modell"))
            logger.info(f"Dual-Model: fast={model_fast}, main={model}")

        for m, label in models_to_warm:
            warmup_model(m, label)

        ollama_ready.set()

    # Start warmup in background thread
    threading.Thread(target=warmup_ollama, daemon=True).start()
    if model_fast and model_fast != model:
        logger.info(f"🐠 Bot startet sofort – 2 Modelle laden im Hintergrund ({model_fast} + {model})")
    else:
        logger.info("🐠 Bot startet sofort – Ollama lädt im Hintergrund.")

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

    # Messages – direct chat, no classifier
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    logger.info(f"Bot läuft. Authorized Chat-ID: {CHAT_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
