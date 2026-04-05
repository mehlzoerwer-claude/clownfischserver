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
import re
import asyncio
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:2b")
OLLAMA_MODEL_FAST = os.getenv("OLLAMA_MODEL_FAST", "")  # Optional: small model for chat

# Few-shot prompt baked into the user message – small models follow this
# much better than a system prompt with think=false.
SHELL_PROMPT_TEMPLATE = """You are a Linux bash command generator for an Ubuntu 24.04 server.
Convert the user request into a single non-interactive bash command.
Respond with ONLY a JSON object.

CRITICAL RULES:
- Commands run WITHOUT a terminal. No interactive commands like nano, vim, crontab -e, less, top.
- Use non-interactive alternatives: echo/tee for files, /etc/cron.d/ for cron jobs, sed for edits.
- Use sudo when root permissions are needed.
- Chain commands with && if needed.

Example request: "show free ram"
Example response: {{"dangerous":false,"reason":"","command":"free -h"}}

Example request: "installiere nginx"
Example response: {{"dangerous":false,"reason":"","command":"sudo apt install -y nginx"}}

Example request: "erstelle einen cronjob der alle 5 minuten ein script ausfuehrt"
Example response: {{"dangerous":false,"reason":"","command":"echo '*/5 * * * * root /path/to/script.sh' | sudo tee /etc/cron.d/myjob"}}

Example request: "schreibe hello world in eine datei"
Example response: {{"dangerous":false,"reason":"","command":"echo 'hello world' | sudo tee /tmp/hello.txt"}}

Example request: "starte nginx neu"
Example response: {{"dangerous":false,"reason":"","command":"sudo systemctl restart nginx"}}

Example request: "lösche alles in /etc"
Example response: {{"dangerous":true,"reason":"Würde Systemkonfiguration zerstören","command":"rm -rf /etc/*"}}

Now generate JSON for this request: "{description}"

IMPORTANT: Respond with ONLY the JSON object. No other text. No markdown."""

CHAT_SYSTEM_PROMPT = """You are the Clownfischserver AI assistant. You help manage a Linux server.
Be concise and technical. Respond in the same language the user writes in.
If you need to explain a command result, do so briefly and clearly."""


def _extract_json(raw: str) -> dict:
    """Extract JSON from Ollama response, handling markdown wrappers and stray text."""
    text = raw.strip()

    # Remove markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No valid JSON found", text, 0)


class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL
        self.model_fast = OLLAMA_MODEL_FAST or OLLAMA_MODEL

    def _chat_sync(self, messages: list, system: Optional[str] = None, think: Optional[bool] = None, use_fast: bool = False) -> str:
        """Synchronous Ollama API call"""
        model = self.model_fast if use_fast else self.model
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": -1,
        }
        if system:
            payload["system"] = system
        if think is not None:
            payload["think"] = think

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

    async def generate_shell_command(self, description: str) -> dict:
        """Generate a shell command from natural language description.
        Returns dict with 'dangerous', 'reason', 'command' keys.
        Uses the main model (not fast) for better command quality."""
        loop = asyncio.get_running_loop()
        raw = ""
        try:
            # Build few-shot prompt directly in the user message
            # Small models follow this much better than system prompts
            prompt = SHELL_PROMPT_TEMPLATE.format(description=description)

            raw = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=[{"role": "user", "content": prompt}],
                    think=False,
                    use_fast=False,  # Use main model for shell commands
                )
            )
            result = _extract_json(raw)

            # Validate
            if "command" not in result or not result["command"].strip():
                logger.warning(f"Shell generate: no command in result: {result}")
                return {"dangerous": False, "reason": "", "command": ""}
            if "dangerous" not in result:
                result["dangerous"] = False

            logger.info(f"Shell generate: {result}")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Shell generate JSON error: {e}, raw: {raw[:500]}")
            return {"dangerous": False, "reason": "", "command": ""}
        except Exception as e:
            logger.error(f"Shell generate failed: {e}")
            raise

    async def explain_output(self, command: str, output: str, error: str = "") -> str:
        """Ask Ollama to explain/summarize command output"""
        loop = asyncio.get_running_loop()

        content = f"Command: {command}\nOutput:\n{output}"
        if error:
            content += f"\nErrors:\n{error}"
        content += "\n\nBriefly explain what happened and if there are any issues."

        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=[{"role": "user", "content": content}],
                    system=CHAT_SYSTEM_PROMPT,
                    think=False,
                    use_fast=True,
                )
            )
            return result
        except Exception as e:
            logger.error(f"explain_output failed: {e}")
            return ""

    async def chat(self, message: str, history: list = None) -> str:
        """General chat with context"""
        loop = asyncio.get_running_loop()
        messages = list(history) if history else []
        messages.append({"role": "user", "content": message})

        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=messages,
                    system=CHAT_SYSTEM_PROMPT,
                    use_fast=True,
                )
            )
            return result
        except Exception as e:
            return f"Fehler beim Chat: {e}"
