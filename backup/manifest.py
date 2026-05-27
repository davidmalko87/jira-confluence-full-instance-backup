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
import zipfile
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"          # combined-mode manifest
MANIFEST_SUFFIX = ".manifest.json"       # per-product: <archive-stem>.manifest.json
SCHEMA_VERSION = 1
_PRODUCTS = ("jira", "confluence")


# Entries that mark a genuine Atlassian site export, so we never archive/upload
# (and later try to restore) an HTML error page or a truncated download.
#   Jira Cloud export  : entities.xml + activeobjects.xml
#   Confluence export  : entities.xml + exportDescriptor.properties
_EXPORT_MARKERS = {
    "jira": ("entities.xml", "activeobjects.xml"),
    "confluence": ("entities.xml", "exportDescriptor.properties"),
}


def verify_export(zip_path: Path, product: str) -> tuple[bool, str]:
    """
    Sanity-check a freshly downloaded export before it's archived/uploaded.

    Returns (ok, message). ok=False means the file is clearly NOT a backup (not a
    ZIP / empty / corrupt) and the caller should fail. ok=True with a message that
    starts "WARNING:" means it IS a ZIP but is missing the entries Atlassian's
    import expects — surfaced so you find out now, not at restore time.
    """
    if not zipfile.is_zipfile(zip_path):
        head = b""
        try:
            head = zip_path.read_bytes()[:80]
        except OSError:
            pass
        return False, (f"not a ZIP archive (starts with {head!r}) — likely an error/"
                       f"login page or a truncated download, not a {product} export")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            bad = zf.testzip()
    except zipfile.BadZipFile as exc:
        return False, f"corrupt ZIP: {exc}"
    if bad is not None:
        return False, f"corrupt entry in ZIP: {bad}"
    if not names:
        return False, "ZIP is empty"

    markers = _EXPORT_MARKERS.get(product, ())
    basenames = {n.rsplit("/", 1)[-1] for n in names}
    missing = [m for m in markers if m not in basenames]
    if "entities.xml" in missing:
        return True, (f"WARNING: valid ZIP but no entities.xml among {len(names)} "
                      f"entries — may be rejected on import as a {product} backup")
    found = [m for m in markers if m in basenames]
    return True, f"valid {product} export ({len(names)} entries; found {found})"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _entry(path: Path) -> dict:
    return {"name": path.name, "size": path.stat().st_size, "sha256": sha256_file(path)}


def _is_manifest(path: Path) -> bool:
    return path.name == MANIFEST_NAME or path.name.endswith(MANIFEST_SUFFIX)


def build_files(sources: list[Path], archive_path: Path, *, site: str = "") -> dict:
    """Build a manifest describing an explicit list of source files + the archive."""
    entries = [_entry(f) for f in sources]
    blob = " ".join(e["name"].lower() for e in entries)
    products = [p for p in _PRODUCTS if p in blob]
    return {
        "schema": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "site": site,
        "products": products,
        "sources": entries,
        "archive": _entry(archive_path),
        "complete": True,
    }


def build(source_dir: Path, archive_path: Path, *, site: str = "") -> dict:
    """Build a manifest for the combined archive (all source files in a dir)."""
    sources = [f for f in sorted(source_dir.glob("*"))
               if f.is_file() and not _is_manifest(f)]
    return build_files(sources, archive_path, site=site)


def write(manifest: dict, archive_dir: Path, name: str = MANIFEST_NAME) -> Path:
    path = archive_dir / name
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def read(archive_dir: Path, name: str = MANIFEST_NAME) -> dict | None:
    path = archive_dir / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def manifest_paths(archive_dir: Path) -> list[Path]:
    """All manifest files in archive_dir: combined manifest.json + per-product ones."""
    if not archive_dir.exists():
        return []
    paths = [p for p in sorted(archive_dir.glob("*.json")) if _is_manifest(p)]
    return paths


def read_all(archive_dir: Path) -> list[dict]:
    """Parse every manifest in archive_dir (combined and/or per-product)."""
    out = []
    for p in manifest_paths(archive_dir):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return out


def _validate_one(archive_dir: Path, man: dict) -> list[str]:
    issues = []
    arch = man.get("archive") or {}
    name = arch.get("name", "")
    target = archive_dir / name
    if not man.get("complete"):
        issues.append(f"{name or '(unnamed)'}: manifest marked incomplete")
    if not name or not target.exists():
        issues.append(f"archive file missing: {name or '(unnamed)'}")
    elif target.stat().st_size != arch.get("size"):
        issues.append(f"size mismatch for {name}")
    elif sha256_file(target) != arch.get("sha256"):
        issues.append(f"sha256 mismatch for {name} — archive corrupt")
    return issues


def validate(archive_dir: Path) -> tuple[bool, list[str]]:
    """Verify every archive in archive_dir against its manifest(s) (sha256)."""
    mans = read_all(archive_dir)
    if not mans:
        return False, ["No manifest found — backup incomplete or missing"]
    issues = []
    for man in mans:
        issues += _validate_one(archive_dir, man)
    return (not issues), issues


def has_complete_today(archive_dir: Path, product: str) -> bool:
    """True if a complete backup for `product` was already made today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for man in read_all(archive_dir):
        if (man.get("complete")
                and (man.get("created_utc") or "")[:10] == today
                and product in man.get("products", [])):
            return True
    return False


def cleanup(out_dir: Path, archive_dir: Path, keep_days: int | None = None) -> list[str]:
    """
    Remove:
      - orphan .7z in archive_dir not referenced by a complete manifest (failed runs)
      - transient source files in out_dir once a complete archive exists
      - anything in archive_dir older than keep_days (if given)
    Returns the list of removed paths.
    """
    removed: list[str] = []
    mans = read_all(archive_dir)
    referenced = {m["archive"]["name"] for m in mans if m.get("archive", {}).get("name")}
    any_complete = any(m.get("complete") for m in mans)

    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.7z")):
            if f.name not in referenced:
                f.unlink()
                removed.append(str(f))

    if any_complete and out_dir.exists():
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
