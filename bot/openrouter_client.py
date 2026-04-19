#!/usr/bin/env python3
"""
🐠 Clownfischserver – OpenRouter Free Models Fallback
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

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Free models on OpenRouter (no credit card needed)
# openrouter/free auto-selects the best available free model
FREE_MODELS = {
    "coder": "openrouter/free",
    "chat": "openrouter/free",
}


def _extract_json(raw: str) -> dict:
    """Extract JSON from response."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No valid JSON found", text, 0)


class OpenRouterClient:
    """OpenRouter Free Models Client – fallback when Ollama times out."""

    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        if self.api_key:
            logger.info("OpenRouter Fallback konfiguriert")
        else:
            logger.info("OpenRouter nicht konfiguriert – Fallback deaktiviert")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _chat_sync(self, messages: list, system: Optional[str] = None, model: str = None) -> str:
        """Synchronous OpenRouter API call."""
        if not self.api_key:
            raise RuntimeError("OpenRouter API Key nicht konfiguriert")

        model = model or FREE_MODELS["chat"]

        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        api_messages.extend(messages)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": api_messages,
                    "temperature": 0.7,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("OpenRouter nicht erreichbar")
        except requests.exceptions.Timeout:
            raise RuntimeError("OpenRouter Timeout")
        except Exception as e:
            raise RuntimeError(f"OpenRouter Fehler: {e}")

    async def generate_shell_command(self, description: str) -> dict:
        """Generate shell command via OpenRouter."""
        loop = asyncio.get_running_loop()

        prompt = (
            "You are a Linux bash command generator for Ubuntu 24.04.\n"
            "Convert the request into a single non-interactive bash command.\n"
            "Respond ONLY with JSON: {\"dangerous\": bool, \"reason\": string, \"command\": string}\n"
            "No interactive commands (nano, vim, crontab -e). Use sudo when needed.\n\n"
            f"Request: {description}\n\nJSON only:"
        )

        try:
            raw = await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=[{"role": "user", "content": prompt}],
                    model=FREE_MODELS["coder"],
                ),
            )
            result = _extract_json(raw)
            if "command" not in result:
                result["command"] = ""
            if "dangerous" not in result:
                result["dangerous"] = False
            logger.info(f"OpenRouter shell: {result}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"OpenRouter JSON error: {e}")
            return {"dangerous": False, "reason": "", "command": ""}
        except Exception as e:
            logger.error(f"OpenRouter shell failed: {e}")
            raise

    async def chat(self, message: str, history: list = None) -> str:
        """General chat via OpenRouter."""
        loop = asyncio.get_running_loop()
        messages = list(history) if history else []
        messages.append({"role": "user", "content": message})

        system = (
            "Du bist der Clownfischserver KI-Assistent. Du hilfst beim Verwalten eines Linux-Servers.\n"
            "Antworte kurz und technisch. Antworte IMMER in der Sprache in der der Nutzer schreibt."
        )

        try:
            return await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=messages,
                    system=system,
                    model=FREE_MODELS["chat"],
                ),
            )
        except Exception as e:
            return f"OpenRouter Fehler: {e}"

    async def explain_output(self, command: str, output: str, error: str = "") -> str:
        """Explain command output via OpenRouter."""
        loop = asyncio.get_running_loop()

        content = f"Command: {command}\nOutput:\n{output}"
        if error:
            content += f"\nErrors:\n{error}"
        content += "\n\nErkläre kurz was passiert ist und ob es Probleme gibt. Antworte in der gleichen Sprache wie der Nutzer."

        try:
            return await loop.run_in_executor(
                None,
                lambda: self._chat_sync(
                    messages=[{"role": "user", "content": content}],
                    model=FREE_MODELS["chat"],
                ),
            )
        except Exception as e:
            logger.error(f"OpenRouter explain failed: {e}")
            return ""
