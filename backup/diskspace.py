"""
Pre-flight disk-space check.

Refuse to start a download we definitely can't fit, and warn when free space is
tight — so an unattended run fails fast and clearly instead of filling the disk
mid-write and leaving a truncated backup. Called right after the download's
Content-Length is known, before any bytes are written.

The floor for the unknown-size case is MIN_FREE_DISK_MB (env, default 500).
"""
import os
import shutil
from pathlib import Path

from . import ui

_MB = 1024 * 1024


def _mb(n: int) -> str:
    return f"{n / _MB:.0f} MB"


def _floor_bytes() -> int:
    try:
        return int(os.environ.get("MIN_FREE_DISK_MB") or 500) * _MB
    except (TypeError, ValueError):
        return 500 * _MB


def precheck(target_dir: Path, needed_bytes: int = 0) -> None:
    """
    Check free space in `target_dir` before writing ~`needed_bytes` (0 = unknown).

    Raises RuntimeError when it definitely won't fit (free < needed); warns when
    it's tight (below MIN_FREE_DISK_MB, or under 2x the known download size — the
    archive + upload steps need transient room too). A stat failure is ignored
    rather than blocking the backup.
    """
    try:
        free = shutil.disk_usage(target_dir).free
    except OSError:
        return

    if needed_bytes and free < needed_bytes:
        raise RuntimeError(
            f"Not enough free disk in {target_dir}: need ~{_mb(needed_bytes)}, "
            f"only {_mb(free)} free (set MIN_FREE_DISK_MB or free up space)")

    if free < _floor_bytes() or (needed_bytes and free < needed_bytes * 2):
        extra = f" (incoming ~{_mb(needed_bytes)})" if needed_bytes else ""
        ui.warn(f"Low disk space: {_mb(free)} free in {target_dir}{extra}")
