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
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

MGMT_USER = os.getenv("MGMT_USER", "clownfish")
COMMAND_TIMEOUT = 120  # seconds


async def execute_command(
    user_message: str,
    ollama_client,
    skip_safety: bool = False
) -> str:
    """
    Execute a shell command derived from user's natural language input.
    Returns combined stdout + stderr + optional explanation.
    """

    if skip_safety:
        # For internal status calls, build command directly
        shell_cmd = _build_status_command(user_message)
    else:
        # Get the shell command from the safety check result
        safety = await ollama_client.safety_check(user_message)

        if safety.get("type") in ("info", "chat"):
            # Question or conversation
            return await ollama_client.chat(user_message)

        shell_cmd = safety.get("shell_command", "").strip()
        if not shell_cmd:
            return await ollama_client.chat(user_message)

    logger.info(f"Executing: {shell_cmd}")

    stdout, stderr, returncode = await _run_shell(shell_cmd)

    # Build response
    response_parts = []

    if shell_cmd:
        response_parts.append(f"$ {shell_cmd}")

    if stdout:
        response_parts.append(stdout)

    if stderr and returncode != 0:
        response_parts.append(f"[STDERR]\n{stderr}")

    if returncode != 0:
        response_parts.append(f"[Exit code: {returncode}]")

    raw_output = "\n".join(response_parts)

    # If there's an error or output is complex, ask Ollama to explain
    if returncode != 0 or (len(stdout) > 500 and not skip_safety):
        explanation = await ollama_client.explain_output(shell_cmd, stdout, stderr)
        if explanation:
            raw_output += f"\n\n💡 {explanation}"

    return raw_output or "✓ Ausgeführt (keine Ausgabe)"


async def _run_shell(command: str) -> tuple[str, str, int]:
    """Run a shell command as mgmt user, return (stdout, stderr, returncode)"""
    try:
        # Run as mgmt user via sudo -u, or directly if already that user
        current_user = os.getenv("USER", "")
        if current_user != MGMT_USER:
            full_cmd = f"sudo -u {MGMT_USER} bash -c {repr(command)}"
        else:
            full_cmd = command

        process = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "HOME": f"/home/{MGMT_USER}"}
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=COMMAND_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            return "", f"Timeout nach {COMMAND_TIMEOUT}s", 1

        return (
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
            process.returncode
        )

    except Exception as e:
        logger.error(f"Shell execution error: {e}")
        return "", str(e), 1


def _build_status_command(message: str) -> str:
    """Build a status command for internal use"""
    message_lower = message.lower()

    if "memory" in message_lower or "ram" in message_lower:
        return "free -h"
    elif "disk" in message_lower or "storage" in message_lower:
        return "df -h"
    elif "cpu" in message_lower or "load" in message_lower:
        return "top -bn1 | head -20"
    elif "uptime" in message_lower:
        return "uptime"
    elif "process" in message_lower or "running" in message_lower:
        return "ps aux --sort=-%cpu | head -20"
    else:
        # Full status
        return (
            "echo '=== UPTIME ===' && uptime && "
            "echo '=== MEMORY ===' && free -h && "
            "echo '=== DISK ===' && df -h && "
            "echo '=== TOP PROCESSES ===' && ps aux --sort=-%cpu | head -10"
        )
