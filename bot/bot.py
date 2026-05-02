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
openrouter = OpenRouterClient()
ollama = OllamaClient(openrouter_client=openrouter)
snapshots = SnapshotManager()
aider = AiderWrapper()

# =============================================================================
# AUTH GUARD + HELPERS
# =============================================================================

def is_authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == CHAT_ID

async def safe_reply(target, text: str, parse_mode: str = "Markdown", edit: bool = False):
    """Send or edit a message. Falls back to plain text if Markdown fails."""
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
    if not is_authorized(update):
        return

    fallback_info = ""
    if openrouter.is_available():
        fallback_info = "\n✅ OpenRouter Fallback aktiv"

    await update.message.reply_text(
        f"🐠 *Clownfischserver v0.5.0 online.*{fallback_info}\n\n"
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
    """Open or close SSH via ufw"""
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
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/shell <was du tun willst>`\n\n"
            "Beispiel: `/shell zeig mir den freien RAM`",
            parse_mode="Markdown"
        )
        return

    if (ollama_ready is None or not ollama_ready.is_set()) and not openrouter.is_available():
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

        if result.get("dangerous", False):
            await safe_reply(thinking_msg,
                f"⚠️ *Gefährlicher Befehl verweigert!*\n\n"
                f"Befehl: `{command}`\n"
                f"Grund: {result.get('reason', 'Zu riskant')}",
                edit=True
            )
            return

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
    if not is_authorized(update):
        return

    pending = context.user_data.get("pending_cmd")
    if not pending:
        await update.message.reply_text("❓ Kein ausstehender Befehl. Nutze erst `/shell <beschreibung>`.", parse_mode="Markdown")
        return

    command = pending
    context.user_data.pop("pending_cmd", None)

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
            f"❌ Fehler:\n`{e}`\n\nSnapshot: `{snap_name or 'keiner'}`",
            edit=True
        )

# =============================================================================
# /code – Aider für Code-Generierung
# =============================================================================

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Smart prompt: ensure Aider creates a FILE, not just chat output
    workspace = os.getenv("AIDER_WORKDIR", "/opt/clownfisch-workspace")
    task_lower = task.lower()

    if workspace not in task and "/opt/" not in task and "/" not in task.split()[0] if task.split() else True:
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

    try:
        result = await aider.run(task)
        if len(result) > 4000:
            result = result[:4000] + "\n... (gekürzt)"
        await safe_reply(status_msg, f"🛠️ Aider Ergebnis:\n\n```\n{result}\n```", edit=True)
    except Exception as e:
        logger.error(f"cmd_code failed: {e}", exc_info=True)
        await safe_reply(status_msg,
            f"❌ Aider Fehler:\n`{e}`\n\nSnapshot: `{snap_name or 'keiner'}`",
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
        await status_msg.edit_text("📂 Entpacke ZIP...")
        extract_dir = os.path.join(tmp_dir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

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
    if not is_authorized(update):
        logger.warning(f"Unauthorized access attempt from chat_id: {update.effective_chat.id}")
        return

    user_message = update.message.text.strip()

    # --- Active update dialog? Handle that first, don't send to chat ---
    update_step = context.user_data.get("update_step")
    if update_step:
        await _handle_update_dialog(update, context, user_message, update_step)
        return

    # --- Normal chat ---
    logger.info(f"Chat message: {user_message[:100]}")

    if (ollama_ready is None or not ollama_ready.is_set()) and not openrouter.is_available():
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
        await thinking_msg.edit_text(f"❌ Chat-Fehler: `{e}`", parse_mode="Markdown")


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
    logger.info("🐠 Clownfischserver v0.5.0 Bot startet...")

    import requests as req
    import time
    import threading

    model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    model_fast = os.getenv("OLLAMA_MODEL_FAST", "")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
        logger.info("Ollama Warmup gestartet (Hintergrund)...")
        models_to_warm = [(model, "Hauptmodell")]
        if model_fast and model_fast != model:
            models_to_warm.insert(0, (model_fast, "Fast-Modell"))
            logger.info(f"Dual-Model: fast={model_fast}, main={model}")
        for m, label in models_to_warm:
            warmup_model(m, label)
        ollama_ready.set()

    threading.Thread(target=warmup_ollama, daemon=True).start()
    if model_fast and model_fast != model:
        logger.info(f"🐠 Bot startet – 2 Modelle laden ({model_fast} + {model})")
    else:
        logger.info("🐠 Bot startet – Ollama lädt im Hintergrund.")

    if openrouter.is_available():
        logger.info("✅ OpenRouter Fallback aktiv")

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

    # Messages – single handler for chat AND update dialog (no double-processing)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    logger.info(f"Bot läuft. Authorized Chat-ID: {CHAT_ID}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
