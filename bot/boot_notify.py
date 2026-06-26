#!/usr/bin/env python3
"""
🐠 Clownfischserver – Boot Notification
Sends a Telegram message after server boot with service status.
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0 – Keep it open. Always.
Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
"""

import os
import subprocess
import sys
from datetime import datetime
from dotenv import load_dotenv
import requests

# Load .env
INSTALL_DIR = os.getenv("INSTALL_DIR", "/opt/clownfischserver")
load_dotenv(os.path.join(INSTALL_DIR, "config", ".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SERVICES = ["clownfisch", "ollama", "ufw", "ssh", "cron"]


def get_service_status(name: str) -> str:
    """Check if a systemd service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5
        )
        status = result.stdout.strip()
        if status == "active":
            return "✅"
        elif status == "inactive":
            return "⚪"
        else:
            return "❌"
    except Exception:
        return "❓"


def get_uptime() -> str:
    """Get system uptime."""
    try:
        result = subprocess.run(
            ["uptime", "-p"], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return "unbekannt"


def get_memory() -> str:
    """Get memory usage."""
    try:
        result = subprocess.run(
            ["free", "-h", "--si"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                return f"{parts[2]} / {parts[1]}"
    except Exception:
        pass
    return "unbekannt"


def send_message(text: str):
    """Send Telegram message."""
    if not BOT_TOKEN or not CHAT_ID:
        print("ERROR: Token oder Chat-ID fehlt in .env")
        sys.exit(1)
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram Fehler: {e}")
        sys.exit(1)


def main():
    zeit = datetime.now().strftime("%H:%M:%S")
    datum = datetime.now().strftime("%d.%m.%Y")

    # Build service status list
    status_lines = []
    for svc in SERVICES:
        icon = get_service_status(svc)
        status_lines.append(f"  {icon} {svc}")

    uptime = get_uptime()
    memory = get_memory()

    msg = (
        f"🐠 *Server gestartet!*\n\n"
        f"Zeit: {datum} {zeit}\n"
        f"Uptime: {uptime}\n"
        f"RAM: {memory}\n\n"
        f"*Dienste:*\n" +
        "\n".join(status_lines)
    )

    send_message(msg)
    print(f"Boot notification sent at {datum} {zeit}")


if __name__ == "__main__":
    main()
