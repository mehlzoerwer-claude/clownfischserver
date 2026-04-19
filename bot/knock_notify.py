#!/usr/bin/env python3
"""
🐠 Clownfischserver
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0 – Keep it open. Always.
Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env
ENV_FILE = "/opt/clownfischserver/config/.env"
load_dotenv(ENV_FILE)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(text: str):
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

if __name__ == "__main__":
    event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    ip = sys.argv[2] if len(sys.argv) > 2 else "unbekannt"

    from datetime import datetime
    zeit = datetime.now().strftime("%H:%M:%S")
    datum = datetime.now().strftime("%d.%m.%Y")

    if event == "open":
        send_message(f"🔓 *SSH geöffnet*\nIP: `{ip}`\nZeit: {datum} {zeit}")
    elif event == "close":
        send_message(f"🔒 *SSH geschlossen*\nIP: `{ip}`\nZeit: {datum} {zeit}")
    elif event == "attempt":
        send_message(f"⚠️ *Knock-Versuch*\nIP: `{ip}`\nZeit: {datum} {zeit}")
