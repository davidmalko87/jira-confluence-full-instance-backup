"""
Backup manifest — a manifest.json written next to the archive when a backup
completes.

Its presence with "complete": true marks the backup as finished (mirrors the
sibling jira-project-backup-restore convention), and it records sha256
checksums so integrity can be verified later and stale/incomplete backups can
be cleaned up safely.
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1
_PRODUCTS = ("jira", "confluence")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _entry(path: Path) -> dict:
    return {"name": path.name, "size": path.stat().st_size, "sha256": sha256_file(path)}


def build(source_dir: Path, archive_path: Path, *, site: str = "") -> dict:
    """Build a manifest describing the source files and the encrypted archive."""
    sources = [_entry(f) for f in sorted(source_dir.glob("*"))
               if f.is_file() and f.name != MANIFEST_NAME]
    blob = " ".join(s["name"].lower() for s in sources)
    products = [p for p in _PRODUCTS if p in blob]
    return {
        "schema": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "site": site,
        "products": products,
        "sources": sources,
        "archive": _entry(archive_path),
        "complete": True,
    }


def write(manifest: dict, archive_dir: Path) -> Path:
    path = archive_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def read(archive_dir: Path) -> dict | None:
    path = archive_dir / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def validate(archive_dir: Path) -> tuple[bool, list[str]]:
    """Verify the archive in archive_dir against its manifest (sha256)."""
    man = read(archive_dir)
    if not man:
        return False, ["No manifest.json found — backup incomplete or missing"]

    issues = []
    if not man.get("complete"):
        issues.append("manifest is marked incomplete")

    arch = man.get("archive") or {}
    name = arch.get("name", "")
    target = archive_dir / name
    if not name or not target.exists():
        issues.append(f"archive file missing: {name or '(unnamed)'}")
    elif target.stat().st_size != arch.get("size"):
        issues.append(f"size mismatch for {name}")
    elif sha256_file(target) != arch.get("sha256"):
        issues.append(f"sha256 mismatch for {name} — archive corrupt")

    return (not issues), issues


def has_complete_today(archive_dir: Path, product: str) -> bool:
    """True if a complete backup for `product` was already made today."""
    man = read(archive_dir)
    if not man or not man.get("complete"):
        return False
    created = (man.get("created_utc") or "")[:10]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return created == today and product in man.get("products", [])


def cleanup(out_dir: Path, archive_dir: Path, keep_days: int | None = None) -> list[str]:
    """
    Remove:
      - orphan .7z in archive_dir not referenced by a complete manifest (failed runs)
      - transient source files in out_dir once a complete archive exists
      - anything in archive_dir older than keep_days (if given)
    Returns the list of removed paths.
    """
    removed: list[str] = []
    man = read(archive_dir)
    referenced = {man["archive"]["name"]} if man and man.get("archive") else set()

    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.7z")):
            if f.name not in referenced:
                f.unlink()
                removed.append(str(f))

    if man and man.get("complete") and out_dir.exists():
        for f in sorted(out_dir.glob("*")):
            if f.is_file():
                f.unlink()
                removed.append(str(f))

    if keep_days and archive_dir.exists():
        cutoff = time.time() - keep_days * 86400
        for f in sorted(archive_dir.glob("*")):
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed.append(str(f))

    return removed
