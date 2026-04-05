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
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL_DIR = os.getenv("INSTALL_DIR", "/opt/clownfischserver")
AIDER_WORKDIR = os.getenv("AIDER_WORKDIR", "/opt/clownfisch-workspace")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:2b")
TIMEOUT = 600  # 10 minutes for aider tasks on CPU


class AiderWrapper:
    def __init__(self):
        self.workdir = Path(AIDER_WORKDIR)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.venv_python = Path(INSTALL_DIR) / "aider-venv" / "bin" / "python3"
        self.venv_aider = Path(INSTALL_DIR) / "aider-venv" / "bin" / "aider"
        logger.info(f"AiderWrapper init: workdir={self.workdir}")

    async def run(self, task: str, target_file: str = None) -> str:
        """
        Run aider in script mode for a coding task.
        Returns the output/result as string.
        """
        logger.info(f"Aider task: {task[:100]}")

        # Determine working directory and files
        workdir = self.workdir

        # Build aider command
        cmd = self._build_aider_command(task, target_file)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                env={
                    **os.environ,
                    "OLLAMA_API_BASE": OLLAMA_BASE_URL,
                    "HOME": f"/home/{os.getenv('MGMT_USER', 'clownfish')}",
                }
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=TIMEOUT
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"⏱️ Aider Timeout nach {TIMEOUT}s. Task zu komplex oder Modell überlastet."

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            # Build response
            result_parts = []

            if stdout_str:
                result_parts.append(stdout_str)

            if stderr_str and process.returncode != 0:
                result_parts.append(f"[STDERR]\n{stderr_str}")

            if process.returncode == 0:
                result_parts.insert(0, f"✅ Aider Task abgeschlossen\nArbeitsverzeichnis: {workdir}\n")
            else:
                result_parts.insert(0, f"⚠️ Aider beendet mit Code {process.returncode}\n")

            return "\n".join(result_parts) or "✓ Task abgeschlossen (keine Ausgabe)"

        except FileNotFoundError:
            return (
                "❌ Aider nicht gefunden. Bitte prüfen:\n"
                f"  ls {self.venv_aider}\n"
                "  Ggf. neu installieren mit: pip install aider-chat"
            )
        except Exception as e:
            logger.error(f"Aider execution error: {e}", exc_info=True)
            return f"❌ Aider Fehler: {e}"

    def _build_aider_command(self, task: str, target_file: str = None) -> list:
        """Build the aider command with appropriate flags"""
        cmd = [
            str(self.venv_aider),
            "--model", f"ollama/{OLLAMA_MODEL}",
            "--no-git",           # Don't require git
            "--yes",              # Auto-confirm all changes
            "--no-pretty",        # Plain output for telegram
            "--no-show-model-warnings",  # Skip env var warnings
            "--no-analytics",     # No analytics prompts
            "--edit-format", "diff",  # Better format for small models
            "--message", task,    # The task as a message
        ]

        if target_file:
            cmd.append(target_file)

        return cmd

    async def list_workspace_files(self) -> str:
        """List files in the aider workspace"""
        try:
            files = list(self.workdir.rglob("*"))
            if not files:
                return f"📁 Workspace {self.workdir} ist leer."

            file_list = "\n".join([
                f"  {'📁' if f.is_dir() else '📄'} {f.relative_to(self.workdir)}"
                for f in sorted(files)[:50]
            ])
            return f"📁 Workspace: {self.workdir}\n\n{file_list}"
        except Exception as e:
            return f"❌ Fehler beim Lesen des Workspace: {e}"
