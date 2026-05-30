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
import shlex

logger = logging.getLogger(__name__)

MGMT_USER = os.getenv("MGMT_USER", "clownfish")
COMMAND_TIMEOUT = 120  # seconds


async def run_shell(command: str) -> tuple[str, str, int]:
    """Run a shell command as mgmt user, return (stdout, stderr, returncode)"""
    try:
        current_user = os.getenv("USER", "")
        if current_user != MGMT_USER:
            full_cmd = f"sudo -u {MGMT_USER} bash -c {shlex.quote(command)}"
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


async def execute_command(shell_cmd: str, ollama_client) -> str:
    """
    Execute a pre-determined shell command and return formatted output.
    Optionally asks Ollama to explain errors or complex output.
    """
    logger.info(f"Executing: {shell_cmd}")

    stdout, stderr, returncode = await run_shell(shell_cmd)

    # Build response
    response_parts = [f"$ {shell_cmd}"]

    if stdout:
        response_parts.append(stdout)

    if stderr and returncode != 0:
        response_parts.append(f"[STDERR]\n{stderr}")

    if returncode != 0:
        response_parts.append(f"[Exit code: {returncode}]")

    raw_output = "\n".join(response_parts)

    # If there's an error or output is complex, ask Ollama to explain
    if returncode != 0 or len(stdout) > 500:
        explanation = await ollama_client.explain_output(shell_cmd, stdout, stderr)
        if explanation:
            raw_output += f"\n\n💡 {explanation}"

    return raw_output or "✓ Ausgeführt (keine Ausgabe)"
