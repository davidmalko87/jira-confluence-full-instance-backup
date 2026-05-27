"""
Archive backup files with 7-Zip.

Two layouts (ARCHIVE_MODE / --mode):
  per-product (default) — one .7z per product backup (jira-<date>.7z,
      confluence-<date>.7z), each with its own <stem>.manifest.json. Restore the
      product you need directly; clear what's in storage.
  combined — a single .7z bundling everything in the input dir + one manifest.json.

By default uses AES-256 with encrypted headers (-mhe=on), which hides filenames
inside the archive — the right posture for cloud-stored backups. Encryption can
be turned off (no password) and the compression level is configurable.

Uses subprocess to call `7z` — pre-installed on the Jenkins build agent.
Set SEVEN_ZIP_PATH if `7z` is not on PATH (e.g. local Windows testing:
"C:\\Program Files\\7-Zip\\7z.exe").
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import manifest, naming, ui


SEVEN_ZIP = os.environ.get("SEVEN_ZIP_PATH", "7z")
DEFAULT_COMPRESSION = 5   # 0=store … 9=ultra


def _run_7z(archive_path: Path, sources: list[str], password: str, level: int) -> int:
    """Invoke 7z to add `sources` into archive_path. Returns archive size in bytes."""
    cmd = [SEVEN_ZIP, "a", "-t7z", f"-mx={level}"]
    if password:
        cmd += ["-mhe=on", f"-p{password}"]       # encrypt headers + data
    cmd += [str(archive_path), *sources]

    enc = "AES-256" if password else "no encryption"
    # Don't print the command — password is in argv
    ui.info(f"Creating {archive_path.name} (7z, mx={level}, {enc})")
    if not password:
        ui.warn("Archive is NOT encrypted — avoid for cloud storage of sensitive data")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            f"7-Zip not found ('{SEVEN_ZIP}'). Install p7zip-full, or set "
            f"SEVEN_ZIP_PATH to the 7z executable."
        )
    if result.returncode != 0:
        raise RuntimeError(f"7z failed (exit {result.returncode}): {result.stderr.strip()}")

    return archive_path.stat().st_size


def archive_directory(src_dir: Path, archive_path: Path, password: str = "",
                      level: int = DEFAULT_COMPRESSION) -> int:
    """Archive everything in src_dir into archive_path (combined mode)."""
    if not src_dir.exists() or not any(src_dir.iterdir()):
        raise RuntimeError(f"Source directory {src_dir} is empty — nothing to archive")
    return _run_7z(archive_path, [str(src_dir) + "/*"], password, level)


def archive_file(src_file: Path, archive_path: Path, password: str = "",
                 level: int = DEFAULT_COMPRESSION) -> int:
    """Archive a single file into archive_path (per-product mode)."""
    return _run_7z(archive_path, [str(src_file)], password, level)


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
                        help="7z compression level: 0=store … 9=ultra (default 5)")
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
