#!/usr/bin/env python3
"""
🐠 Clownfischserver
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0 – Keep it open. Always.
Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
"""

import logging
import os
import subprocess
import shutil
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "/opt/clownfisch-snapshots")
SNAPSHOT_METHOD = os.getenv("SNAPSHOT_METHOD", "tar")
MAX_SNAPSHOTS = 20  # Auto-cleanup limit (kept snapshots are exempt)
KEPT_FILE = os.path.join(SNAPSHOT_DIR, ".kept.json")  # Tracks important snapshots

# Commands that trigger automatic snapshots
AUTO_SNAPSHOT_TRIGGERS = [
    "apt install", "apt-get install", "apt remove", "apt-get remove",
    "apt upgrade", "apt-get upgrade", "dnf install", "dnf remove",
    "pacman -S", "pacman -R",
    "systemctl enable", "systemctl disable",
    "rm -", "mv ", "cp -",
    "chmod ", "chown ",
    "nano ", "vim ", "vi ", "echo >", "tee ",
    "dd ", "mkfs", "fdisk",
]

# Commands that are always read-only – never need a snapshot
READONLY_PREFIXES = [
    "ls", "cat ", "grep ", "find ", "df ", "du ", "free",
    "top", "ps ", "who", "uptime", "journalctl", "tail ",
    "head ", "wc ", "stat ", "file ", "which ", "type ",
    "systemctl status", "systemctl is-active", "systemctl show",
    "ollama list", "docker ps", "docker images",
]


def should_snapshot(command: str) -> bool:
    """Check if a shell command warrants an automatic snapshot."""
    cmd_lower = command.lower().strip()

    # Skip read-only commands
    for ro in READONLY_PREFIXES:
        if cmd_lower.startswith(ro):
            return False

    # Check triggers
    for trigger in AUTO_SNAPSHOT_TRIGGERS:
        if trigger in cmd_lower:
            return True

    return False


class SnapshotManager:
    def __init__(self):
        self.snapshot_dir = Path(SNAPSHOT_DIR)
        self.method = SNAPSHOT_METHOD
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._load_kept()
        logger.info(f"SnapshotManager init: method={self.method}, dir={self.snapshot_dir}")

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    def _load_kept(self):
        """Load list of kept (important) snapshots."""
        try:
            if os.path.exists(KEPT_FILE):
                with open(KEPT_FILE, "r") as f:
                    self.kept = set(json.loads(f.read()))
            else:
                self.kept = set()
        except Exception:
            self.kept = set()

    def _save_kept(self):
        """Save kept snapshots list."""
        try:
            with open(KEPT_FILE, "w") as f:
                json.dump(list(self.kept), f)
        except Exception as e:
            logger.error(f"Could not save kept list: {e}")

    def create_snapshot(self, label: str = "") -> Optional[str]:
        """Create a snapshot. Returns snapshot name or None on failure."""
        name = self._timestamp()
        if label:
            name += f"_{label}"

        try:
            result = self._create_tar_snapshot(name)
            if result:
                logger.info(f"Snapshot created: {name}")
                self._cleanup_old_snapshots()
                return name
            return None
        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            return None

    def _create_tar_snapshot(self, name: str) -> bool:
        """Create tar.gz snapshot, excluding sensitive files."""
        snap_path = self.snapshot_dir / f"{name}.tar.gz"

        # Save current package list for rollback comparison
        pkg_list = self.snapshot_dir / f"{name}.packages.txt"
        try:
            with open(pkg_list, "w") as f:
                subprocess.run(
                    ["dpkg", "--get-selections"],
                    stdout=f,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
        except Exception as e:
            logger.warning(f"Could not save package list: {e}")

        workspace = os.getenv("AIDER_WORKDIR", "/opt/clownfisch-workspace")

        dirs_to_backup = [
            "/etc",
            "/opt/clownfischserver",
            "/home",
            workspace,
        ]
        existing = [d for d in dirs_to_backup if os.path.exists(d)]

        if not existing:
            raise Exception("Keine Verzeichnisse zum Sichern gefunden")

        cmd = ["sudo", "tar", "czf", str(snap_path)]
        cmd += ["--ignore-failed-read"]
        # Exclude sensitive files – NEVER backup secrets
        cmd += ["--exclude=/etc/ssh/ssh_host_rsa_key"]
        cmd += ["--exclude=/etc/ssh/ssh_host_ecdsa_key"]
        cmd += ["--exclude=/etc/ssh/ssh_host_ed25519_key"]
        cmd += ["--exclude=/etc/shadow"]
        cmd += ["--exclude=/etc/gshadow"]
        cmd += ["--exclude=*/config/.env"]  # Don't backup API keys/tokens
        # Exclude large caches
        cmd += ["--exclude=__pycache__"]
        cmd += ["--exclude=*.pyc"]
        cmd += ["--exclude=node_modules"]
        cmd += existing

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode not in (0, 1):  # 1 = warnings only
            raise Exception(result.stderr.decode())
        return True

    def list_snapshots(self) -> list[dict]:
        """List all snapshots with metadata, newest first."""
        try:
            snaps = []
            for f in self.snapshot_dir.iterdir():
                if f.name.endswith(".tar.gz"):
                    name = f.name.replace(".tar.gz", "")
                    size_mb = f.stat().st_size // (1024 * 1024)
                    kept = name in self.kept
                    snaps.append({
                        "name": name,
                        "size_mb": size_mb,
                        "kept": kept
                    })
            snaps.sort(key=lambda x: x["name"], reverse=True)
            return snaps
        except Exception as e:
            logger.error(f"list_snapshots failed: {e}")
            return []

    def keep_snapshot(self, name: str) -> str:
        """Mark a snapshot as important (won't be auto-deleted)."""
        snaps = [s["name"] for s in self.list_snapshots()]
        if name not in snaps:
            return f"❌ Snapshot '{name}' nicht gefunden."
        self.kept.add(name)
        self._save_kept()
        return f"⭐ Snapshot '{name}' als wichtig markiert – wird nicht automatisch gelöscht."

    def unkeep_snapshot(self, name: str) -> str:
        """Remove important mark from snapshot."""
        self.kept.discard(name)
        self._save_kept()
        return f"✅ Markierung von '{name}' entfernt."

    def delete_snapshot(self, name: str) -> str:
        """Delete a specific snapshot."""
        snap_path = self.snapshot_dir / f"{name}.tar.gz"
        pkg_path = self.snapshot_dir / f"{name}.packages.txt"
        if not snap_path.exists():
            return f"❌ Snapshot '{name}' nicht gefunden."
        try:
            snap_path.unlink()
            if pkg_path.exists():
                pkg_path.unlink()
            self.kept.discard(name)
            self._save_kept()
            return f"🗑️ Snapshot '{name}' gelöscht."
        except Exception as e:
            return f"❌ Fehler beim Löschen: {e}"

    def rollback(self, snapshot_name: str) -> str:
        """Roll back to a specific snapshot."""
        snap_path = self.snapshot_dir / f"{snapshot_name}.tar.gz"
        if not snap_path.exists():
            return f"❌ Snapshot '{snapshot_name}' nicht gefunden."
        try:
            tmp_dir = tempfile.mkdtemp()

            # Extract all content
            result = subprocess.run(
                ["sudo", "tar", "xzf", str(snap_path), "-C", tmp_dir],
                capture_output=True
            )
            if result.returncode not in (0, 1):
                raise Exception(f"tar extract failed: {result.stderr.decode()}")

            restored = []

            etc_backup = os.path.join(tmp_dir, "etc")
            if os.path.exists(etc_backup):
                subprocess.run(["sudo", "rsync", "-av", "--delete",
                    etc_backup + "/", "/etc/"], capture_output=True)
                restored.append("/etc")

            cfs_backup = os.path.join(tmp_dir, "opt/clownfischserver")
            if os.path.exists(cfs_backup):
                subprocess.run(["sudo", "rsync", "-av", "--delete",
                    cfs_backup + "/", "/opt/clownfischserver/"], capture_output=True)
                restored.append("/opt/clownfischserver")

            home_backup = os.path.join(tmp_dir, "home")
            if os.path.exists(home_backup):
                subprocess.run(["sudo", "rsync", "-av", "--delete",
                    home_backup + "/", "/home/"], capture_output=True)
                restored.append("/home")

            workspace = os.getenv("AIDER_WORKDIR", "/opt/clownfisch-workspace")
            ws_backup = os.path.join(tmp_dir, workspace.lstrip("/"))
            if os.path.exists(ws_backup):
                subprocess.run(["sudo", "rsync", "-av", "--delete",
                    ws_backup + "/", workspace + "/"], capture_output=True)
                restored.append(workspace)

            shutil.rmtree(tmp_dir, ignore_errors=True)

            restored_str = ", ".join(restored) if restored else "nichts"

            # Check if package list exists for this snapshot
            pkg_hint = ""
            pkg_path = self.snapshot_dir / f"{snapshot_name}.packages.txt"
            if pkg_path.exists():
                pkg_hint = "\n\n💡 Paketliste verfügbar – prüfe mit:\n/run diff <(dpkg --get-selections) " + str(pkg_path)

            return (
                f"✅ Rollback zu '{snapshot_name}' abgeschlossen.\n"
                f"Wiederhergestellt: {restored_str}\n"
                f"Dienste neu starten: systemctl restart clownfisch ollama"
                f"{pkg_hint}"
            )
        except Exception as e:
            return f"❌ Rollback Fehler: {e}"

    def _cleanup_old_snapshots(self):
        """Remove oldest snapshots if over MAX_SNAPSHOTS, skip kept ones."""
        snaps = self.list_snapshots()
        deletable = [s for s in snaps if not s["kept"]]
        if len(deletable) > MAX_SNAPSHOTS:
            to_delete = deletable[MAX_SNAPSHOTS:]
            for snap in to_delete:
                snap_path = self.snapshot_dir / f"{snap['name']}.tar.gz"
                pkg_path = self.snapshot_dir / f"{snap['name']}.packages.txt"
                try:
                    snap_path.unlink()
                    if pkg_path.exists():
                        pkg_path.unlink()
                    logger.info(f"Auto-cleanup: {snap['name']}")
                except Exception as e:
                    logger.warning(f"Could not delete {snap['name']}: {e}")
