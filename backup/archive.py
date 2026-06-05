"""
Archive backup files into encrypted .7z — pure-Python via py7zr (no 7-Zip binary).

Two layouts (ARCHIVE_MODE / --mode):
  per-product (default) — one .7z per product backup (jira-<date>.7z,
      confluence-<date>.7z), each with its own <stem>.manifest.json. Restore the
      product you need directly; clear what's in storage.
  combined — a single .7z bundling everything in the input dir + one manifest.json.

By default uses AES-256 with encrypted headers, which hides the filenames inside
the archive — the right posture for cloud-stored backups. Encryption can be
turned off (no password) and the compression level is configurable.

Archiving is pure-Python (py7zr), so no external 7-Zip binary is required — handy
in bare containers. The produced .7z files are standard and open with any
7-Zip-compatible tool (or py7zr) at restore time.
"""
import argparse
import os
import sys
from pathlib import Path

import py7zr
from py7zr import FILTER_COPY, FILTER_CRYPTO_AES256_SHA256, FILTER_LZMA2

from . import manifest, naming, ui


DEFAULT_COMPRESSION = 5   # 0=store … 9=ultra


def _filters(level: int, encrypt: bool) -> list[dict]:
    """py7zr filter chain: store (level 0) or LZMA2 (1-9), + AES-256 if encrypting."""
    chain = [{"id": FILTER_COPY}] if level <= 0 else [{"id": FILTER_LZMA2, "preset": level}]
    if encrypt:
        chain.append({"id": FILTER_CRYPTO_AES256_SHA256})
    return chain


def _pack(archive_path: Path, files: list[Path], password: str, level: int) -> int:
    """Create archive_path containing `files` (each stored at its basename).

    AES-256 with encrypted headers when `password` is set (hides the filenames —
    the right posture for cloud-stored backups). Returns the archive size in bytes.
    """
    encrypt = bool(password)
    enc = "AES-256" if encrypt else "no encryption"
    ui.info(f"Creating {archive_path.name} (py7zr, level={level}, {enc})")
    if not encrypt:
        ui.warn("Archive is NOT encrypted — avoid for cloud storage of sensitive data")

    kwargs: dict = {"filters": _filters(level, encrypt)}
    if encrypt:
        kwargs["password"] = password
        kwargs["header_encryption"] = True
    with py7zr.SevenZipFile(archive_path, "w", **kwargs) as z:
        for f in files:
            z.write(f, arcname=Path(f).name)
    return archive_path.stat().st_size


def archive_directory(src_dir: Path, archive_path: Path, password: str = "",
                      level: int = DEFAULT_COMPRESSION) -> int:
    """Archive every file in src_dir into archive_path (combined mode)."""
    files = [f for f in sorted(src_dir.glob("*")) if f.is_file()]
    if not files:
        raise RuntimeError(f"Source directory {src_dir} is empty — nothing to archive")
    return _pack(archive_path, files, password, level)


def archive_file(src_file: Path, archive_path: Path, password: str = "",
                 level: int = DEFAULT_COMPRESSION) -> int:
    """Archive a single file into archive_path (per-product mode)."""
    return _pack(archive_path, [src_file], password, level)


def run_archive(in_dir: Path, out_dir: Path, password: str = "",
                name_template: str = naming.DEFAULT_ARCHIVE_TEMPLATE,
                site: str | None = None,
                level: int = DEFAULT_COMPRESSION,
                mode: str = "per-product") -> list[Path]:
    """
    Archive in_dir into out_dir (encrypted iff password). Returns the .7z path(s).

    mode="per-product" (default): one .7z per source .zip, each named after the
      source (jira-<date>.7z) with its own <stem>.manifest.json.
    mode="combined": one .7z bundling everything + a single manifest.json.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    if mode == "combined":
        archive_path = out_dir / naming.render_name(name_template, "atlassian",
                                                    ext=".7z", site=site)
        size = archive_directory(in_dir, archive_path, password, level)
        ui.ok(f"Archive: {archive_path} ({size / (1024 * 1024):.1f} MB)")
        man = manifest.build(in_dir, archive_path, site=site or "")
        man["encrypted"] = bool(password)
        manifest.write(man, out_dir)
        ui.info(f"Manifest: {manifest.MANIFEST_NAME} "
                f"({len(man['sources'])} source file(s), complete)")
        return [archive_path]

    # per-product: one .7z (+ manifest) per product backup .zip
    zips = sorted(in_dir.glob("*.zip"))
    if not zips:
        raise RuntimeError(
            f"No product .zip backups found in {in_dir} — nothing to archive")
    archives: list[Path] = []
    for src in zips:
        archive_path = out_dir / f"{src.stem}.7z"
        size = archive_file(src, archive_path, password, level)
        ui.ok(f"Archive: {archive_path} ({size / (1024 * 1024):.1f} MB)")
        man = manifest.build_files([src], archive_path, site=site or "")
        man["encrypted"] = bool(password)
        man_name = f"{src.stem}{manifest.MANIFEST_SUFFIX}"
        manifest.write(man, out_dir, name=man_name)
        ui.info(f"Manifest: {man_name} (complete)")
        archives.append(archive_path)
    return archives


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", required=True, type=Path)
    parser.add_argument("--out", dest="out_dir", required=True, type=Path)
    parser.add_argument("--name-template",
                        default=os.environ.get("ARCHIVE_NAME_TEMPLATE",
                                               naming.DEFAULT_ARCHIVE_TEMPLATE),
                        help="Archive filename template (tokens: {product}{site}"
                             "{date}{time}{datetime}{timestamp})")
    parser.add_argument("--compression", type=int, choices=range(0, 10),
                        metavar="0-9",
                        default=int(os.environ.get("ARCHIVE_COMPRESSION",
                                                   DEFAULT_COMPRESSION)),
                        help="Compression level: 0=store … 9=ultra (default 5)")
    parser.add_argument("--no-encrypt", action="store_true",
                        help="Create an unencrypted archive (ignore ARCHIVE_PASSWORD)")
    parser.add_argument("--mode", choices=["per-product", "combined"],
                        default=os.environ.get("ARCHIVE_MODE", "per-product"),
                        help="per-product (default): one .7z per product backup; "
                             "combined: a single .7z. Env: ARCHIVE_MODE")
    args = parser.parse_args()

    password = "" if args.no_encrypt else os.environ.get("ARCHIVE_PASSWORD", "")

    try:
        run_archive(args.in_dir, args.out_dir, password,
                    name_template=args.name_template,
                    site=os.environ.get("SITE_JIRA"),
                    level=args.compression, mode=args.mode)
    except (RuntimeError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
