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
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "/opt/clownfisch-snapshots")
SNAPSHOT_METHOD = os.getenv("SNAPSHOT_METHOD", "tar")
MAX_SNAPSHOTS = 50  # Auto-cleanup after this many


class SnapshotManager:
    def __init__(self):
        self.snapshot_dir = Path(SNAPSHOT_DIR)
        self.method = SNAPSHOT_METHOD
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"SnapshotManager init: method={self.method}, dir={self.snapshot_dir}")

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    def create_snapshot(self, label: str = "") -> Optional[str]:
        """Create a snapshot. Returns snapshot name or None on failure."""
        name = self._timestamp()
        if label:
            name += f"_{label}"

        try:
            if self.method == "btrfs":
                result = self._create_btrfs_snapshot(name)
            else:
                result = self._create_tar_snapshot(name)

            if result:
                logger.info(f"Snapshot created: {name}")
                self._cleanup_old_snapshots()
                return name
            return None

        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            return None

    def _create_btrfs_snapshot(self, name: str) -> bool:
        """Create a btrfs snapshot of root subvolume"""
        snap_path = self.snapshot_dir / name
        try:
            subprocess.run(
                ["btrfs", "subvolume", "snapshot", "/", str(snap_path)],
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"btrfs snapshot failed: {e.stderr.decode()}")
            return False

    def _create_tar_snapshot(self, name: str) -> bool:
        """Create tar.gz snapshot of important directories"""
        snap_path = self.snapshot_dir / f"{name}.tar.gz"

        # Directories to snapshot (important config/app dirs, not entire system)
        dirs_to_backup = [
            "/etc",
            "/opt/clownfischserver",
            "/home",
            "/var/spool/cron",
        ]

        # Filter to existing dirs
        existing = [d for d in dirs_to_backup if os.path.exists(d)]

        try:
            with tarfile.open(str(snap_path), "w:gz") as tar:
                for d in existing:
                    tar.add(d, arcname=d.lstrip("/"), recursive=True)
            logger.info(f"tar.gz snapshot: {snap_path} ({snap_path.stat().st_size // 1024}KB)")
            return True
        except Exception as e:
            logger.error(f"tar snapshot failed: {e}")
            if snap_path.exists():
                snap_path.unlink()
            return False

    def list_snapshots(self) -> list[str]:
        """List all available snapshots, newest first"""
        try:
            if self.method == "btrfs":
                snaps = [
                    d.name for d in self.snapshot_dir.iterdir()
                    if d.is_dir()
                ]
            else:
                snaps = [
                    f.stem for f in self.snapshot_dir.iterdir()
                    if f.suffix == ".gz" and f.name.endswith(".tar.gz")
                ]
                # Fix: handle double extension
                snaps = [
                    f.name.replace(".tar.gz", "")
                    for f in self.snapshot_dir.iterdir()
                    if f.name.endswith(".tar.gz")
                ]

            snaps.sort(reverse=True)
            return snaps
        except Exception as e:
            logger.error(f"list_snapshots failed: {e}")
            return []

    def rollback(self, snapshot_name: str) -> str:
        """Roll back to a specific snapshot"""
        try:
            if self.method == "btrfs":
                return self._rollback_btrfs(snapshot_name)
            else:
                return self._rollback_tar(snapshot_name)
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return f"❌ Rollback fehlgeschlagen: {e}"

    def _rollback_btrfs(self, name: str) -> str:
        snap_path = self.snapshot_dir / name
        if not snap_path.exists():
            return f"❌ Snapshot '{name}' nicht gefunden."

        try:
            # For btrfs rollback we'd need to swap subvolumes
            # This is a simplified version - production needs more care
            subprocess.run(
                ["btrfs", "subvolume", "snapshot", str(snap_path), f"/rollback_{name}"],
                check=True, capture_output=True
            )
            return (
                f"✅ btrfs Snapshot '{name}' bereit.\n"
                f"⚠️ Für vollständigen Rollback: Server neu booten und in fstab auf neues Subvolume zeigen.\n"
                f"Snapshot unter: /rollback_{name}"
            )
        except subprocess.CalledProcessError as e:
            return f"❌ btrfs Rollback Fehler: {e.stderr.decode()}"

    def _rollback_tar(self, name: str) -> str:
        snap_path = self.snapshot_dir / f"{name}.tar.gz"
        if not snap_path.exists():
            return f"❌ Snapshot '{name}' nicht gefunden."

        try:
            # Extract to temp location first for safety
            temp_dir = f"/tmp/rollback_{name}"
            os.makedirs(temp_dir, exist_ok=True)

            with tarfile.open(str(snap_path), "r:gz") as tar:
                # Only restore /etc and /opt (safer than full restore)
                members = [m for m in tar.getmembers()
                          if m.name.startswith(("etc/", "opt/clownfischserver"))]
                tar.extractall(path=temp_dir, members=members)

            # Restore /etc
            etc_backup = os.path.join(temp_dir, "etc")
            if os.path.exists(etc_backup):
                subprocess.run(
                    ["rsync", "-av", "--delete", etc_backup + "/", "/etc/"],
                    capture_output=True
                )

            # Restore clownfischserver
            cfs_backup = os.path.join(temp_dir, "opt/clownfischserver")
            if os.path.exists(cfs_backup):
                subprocess.run(
                    ["rsync", "-av", "--delete", cfs_backup + "/", "/opt/clownfischserver/"],
                    capture_output=True
                )

            # Cleanup temp
            subprocess.run(["rm", "-rf", temp_dir], capture_output=True)

            return (
                f"✅ Rollback zu '{name}' abgeschlossen.\n"
                f"/etc und /opt/clownfischserver wiederhergestellt.\n"
                f"Dienste neu starten mit: systemctl restart clownfisch ollama"
            )
        except Exception as e:
            return f"❌ Rollback Fehler: {e}"

    def _cleanup_old_snapshots(self):
        """Remove oldest snapshots if over MAX_SNAPSHOTS"""
        snaps = self.list_snapshots()
        if len(snaps) > MAX_SNAPSHOTS:
            to_delete = snaps[MAX_SNAPSHOTS:]
            for snap in to_delete:
                try:
                    if self.method == "btrfs":
                        snap_path = self.snapshot_dir / snap
                        subprocess.run(
                            ["btrfs", "subvolume", "delete", str(snap_path)],
                            capture_output=True
                        )
                    else:
                        snap_path = self.snapshot_dir / f"{snap}.tar.gz"
                        if snap_path.exists():
                            snap_path.unlink()
                    logger.info(f"Cleaned up old snapshot: {snap}")
                except Exception as e:
                    logger.warning(f"Could not delete snapshot {snap}: {e}")
