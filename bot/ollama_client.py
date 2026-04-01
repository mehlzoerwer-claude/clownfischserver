#!/usr/bin/env python3
"""
🐠 Clownfischserver
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0 – Keep it open. Always.
Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
"""

import json
import logging
import os
import asyncio
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:2b")

SAFETY_SYSTEM_PROMPT = """You are a safety guard and intent classifier for a Linux server management bot.
Your ONLY job is to analyze user requests and classify them.

Respond ONLY with a JSON object. No text before or after. No markdown. No explanations.

JSON format:
{
  "dangerous": true/false,
  "reason": "why it is dangerous, or empty string",
  "suggestion": "safer alternative, or empty string",
  "type": "shell" or "aider" or "chat",
  "shell_command": "the actual bash command to run, or empty string"
}

Classification rules:

type="chat" when:
- The message is a question, greeting, or general conversation
- Examples: "hi", "who are you", "what can you do", "wer bist du", "was kannst du",
  "how does X work", "explain X", "was ist X", "help", "hilfe"
- shell_command must be empty string for chat

type="shell" when:
- The message asks to DO something on the server
- Examples: "show disk usage", "restart nginx", "list files in /etc",
  "how much ram is free", "zeige prozesse", "installiere docker"
- shell_command must contain the actual bash command

type="aider" when:
- The message asks to write, create, or edit code or files
- Examples: "write a python script", "create a config file", "edit server.js"
- shell_command must be empty string for aider

dangerous=true ONLY for:
- rm -rf on system directories (/etc /boot /usr /bin /lib /proc /sys /)
- wiping disks (dd if=/dev/zero, mkfs on mounted drives)
- fork bombs
- permanently killing sshd or clownfisch service with no recovery
- anything that would make the server permanently unreachable

dangerous=false for everything else including installing packages,
restarting services, viewing logs, editing config files, writing code.

Always respond in the same language the user wrote in.
Never add text outside the JSON object."""

CHAT_SYSTEM_PROMPT = """You are the Clownfischserver AI assistant. You help manage a Linux server.
Be concise and technical. Respond in the same language the user writes in.
If you need to explain a command result, do so briefly and clearly."""


class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL

    def _chat_sync(self, messages: list, system: Optional[str] = None) -> str:
        """Synchronous Ollama API call"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": -1,
        }
        if system:
            payload["system"] = system

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=180
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("Ollama nicht erreichbar – läuft der Service? (systemctl status ollama)")
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama Timeout – Modell lädt möglicherweise noch.")
        except Exception as e:
            raise RuntimeError(f"Ollama Fehler: {e}")

    async def safety_check(self, user_message: str) -> dict:
        """Check if a user request is safe to execute"""
        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=[{"role": "user", "content": user_message}],
                    system=SAFETY_SYSTEM_PROMPT
                )
            )
            # Clean potential markdown wrappers
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)
            logger.info(f"Safety check result: {result}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Safety check JSON parse error: {e}, raw: {raw}")
            # Fallback: safe, treat as shell
            return {
                "dangerous": False,
                "reason": "",
                "suggestion": "",
                "type": "shell",
                "shell_command": user_message
            }
        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            return {
                "dangerous": True,
                "reason": f"Safety check konnte nicht durchgeführt werden: {e}",
                "suggestion": "Bitte später erneut versuchen.",
                "type": "shell",
                "shell_command": ""
            }

    async def explain_output(self, command: str, output: str, error: str = "") -> str:
        """Ask Ollama to explain/summarize command output"""
        loop = asyncio.get_event_loop()

        content = f"Command: {command}\nOutput:\n{output}"
        if error:
            content += f"\nErrors:\n{error}"
        content += "\n\nBriefly explain what happened and if there are any issues."

        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=[{"role": "user", "content": content}],
                    system=CHAT_SYSTEM_PROMPT
                )
            )
            return result
        except Exception as e:
            logger.error(f"explain_output failed: {e}")
            return ""

    async def chat(self, message: str, history: list = None) -> str:
        """General chat with context"""
        loop = asyncio.get_event_loop()
        messages = history or []
        messages.append({"role": "user", "content": message})

        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=messages,
                    system=CHAT_SYSTEM_PROMPT
                )
            )
            return result
        except Exception as e:
            return f"Fehler beim Chat: {e}"
