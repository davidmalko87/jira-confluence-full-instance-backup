#!/usr/bin/env python3
"""
Atlassian full-instance backup — dual-mode entrypoint.

Interactive (run on a VM):
    python main.py

Automation (Jenkins / cron):
    python main.py --all
    python main.py --backup jira,confluence --archive --upload --notify
    python main.py --all --dry-run            # preview, no API calls / no cooldown burn
    python main.py --backup jira --skip-existing
    python main.py --validate                 # check the archive against its manifest
    python main.py --cleanup --keep-days 28    # remove incomplete + old local backups
    python main.py --test-connection
    python main.py --show-config
    python main.py --configure

Config comes from environment variables, optionally hydrated from a .env file
(see .env.example). Exit codes: 0 success, 1 generic failure, 2 human action
needed (e.g. refresh Jira cookies).
"""
import argparse
import sys
from pathlib import Path

from backup import (archive, config, confluence, jira, manifest, naming,
                    notify, ui, upload)

DEFAULT_OUT = Path("out")
DEFAULT_ARCHIVE = Path("archive")
WEBHOOK_CHANNEL_HINTS = ("chat", "slack", "discord", "teams", "webhook")


# ─────────────────────────── orchestration steps ───────────────────────────

def do_backup(cfg: config.Config, products: list[str], out_dir: Path,
              archive_dir: Path, *, skip_existing: bool = False,
              dry_run: bool = False) -> list[str]:
    """Run the requested product backups. Returns list of products that failed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = []

    if "jira" in products:
        ui.section("Jira backup")
        if skip_existing and manifest.has_complete_today(archive_dir, "jira"):
            ui.info("Skipping Jira — complete backup already exists today")
        elif dry_run:
            ui.info(f"[DRY] would trigger Jira backup on {cfg.site_jira}")
        else:
            cookies = jira.cookies_from_blob(cfg.jira_cookies)
            missing = jira.missing_cookies(cookies)
            if not cfg.jira_cookies or missing:
                ui.error(f"Jira cookies missing/invalid: {missing or 'JIRA_COOKIES not set'}")
                errors.append("jira")
            else:
                jira.run_backup(cfg.site_jira, cookies, out_dir,
                                name_template=cfg.product_name_template)

    if "confluence" in products:
        ui.section("Confluence backup")
        if skip_existing and manifest.has_complete_today(archive_dir, "confluence"):
            ui.info("Skipping Confluence — complete backup already exists today")
        elif dry_run:
            ui.info(f"[DRY] would trigger Confluence backup on {cfg.site_confluence}")
        elif not (cfg.atl_email and cfg.atl_token):
            ui.error("ATL_EMAIL / ATL_TOKEN not set")
            errors.append("confluence")
        else:
            confluence.run_backup(cfg.site_confluence, cfg.atl_email, cfg.atl_token,
                                  out_dir, name_template=cfg.product_name_template)
    return errors


def do_archive(cfg: config.Config, out_dir: Path, archive_dir: Path, *,
               dry_run: bool = False, no_encrypt: bool = False) -> Path | None:
    ui.section("Archive (7z)")
    try:
        level = int(cfg.archive_compression)
        if not 0 <= level <= 9:
            level = archive.DEFAULT_COMPRESSION
    except (TypeError, ValueError):
        level = archive.DEFAULT_COMPRESSION
    password = "" if no_encrypt else cfg.archive_password

    if dry_run:
        name = naming.render_name(cfg.archive_name_template, "atlassian",
                                  ext=".7z", site=cfg.site_jira)
        enc = "AES-256" if password else "unencrypted"
        ui.info(f"[DRY] would archive {out_dir} -> {archive_dir / name} "
                f"(mx={level}, {enc}, + manifest)")
        return None
    return archive.run_archive(out_dir, archive_dir, password,
                               name_template=cfg.archive_name_template,
                               site=cfg.site_jira, level=level)


def do_upload(cfg: config.Config, archive_dir: Path, *, dry_run: bool = False) -> None:
    ui.section(f"Upload ({cfg.storage_provider})")
    if dry_run:
        n = len(list(archive_dir.glob("*.7z"))) if archive_dir.exists() else 0
        ui.info(f"[DRY] would upload {n} archive(s) + manifest to "
                f"{cfg.storage_provider}:{cfg.storage_dest}")
        return
    if not cfg.storage_dest:
        raise RuntimeError("STORAGE_DEST not set")
    upload.run_upload(cfg.storage_provider, cfg.storage_dest, archive_dir,
                      endpoint_url=cfg.s3_endpoint_url or None,
                      region=cfg.aws_default_region or None)


def do_notify(cfg: config.Config, status: str, archive_dir: Path,
              build_url: str = "", *, dry_run: bool = False) -> None:
    ui.section("Notify")
    if dry_run:
        ui.info(f"[DRY] would notify channels={cfg.notify_channels} status={status}")
        return
    channels = [c.strip() for c in cfg.notify_channels.split(",") if c.strip()]
    report = notify.build_report(status, archive_dir, build_url)
    failures = notify.dispatch(channels, report, cfg.notify_webhook_url)
    if failures:
        ui.warn(f"{failures} channel(s) failed")


def do_validate(archive_dir: Path) -> bool:
    ui.section("Validate backup")
    ok, issues = manifest.validate(archive_dir)
    if ok:
        ui.ok("Backup valid: manifest complete and archive checksum matches")
    else:
        for issue in issues:
            ui.error(issue)
    return ok


def do_cleanup(out_dir: Path, archive_dir: Path, keep_days: int | None) -> None:
    ui.section("Cleanup backups")
    removed = manifest.cleanup(out_dir, archive_dir, keep_days)
    for path in removed:
        ui.info(f"removed {path}")
    ui.ok(f"Cleaned {len(removed)} item(s)") if removed else ui.info("Nothing to clean")


def do_test(cfg: config.Config) -> bool:
    ui.section("Connection test")
    ok_j, msg_j = (jira.test_connection(cfg.site_jira, cfg.jira_cookies)
                   if cfg.jira_cookies else (False, "JIRA_COOKIES not set"))
    (ui.ok if ok_j else ui.error)(f"Jira: {msg_j}")
    ok_c, msg_c = confluence.test_connection(cfg.site_confluence, cfg.atl_email, cfg.atl_token)
    (ui.ok if ok_c else ui.error)(f"Confluence: {msg_c}")
    return ok_j and ok_c


def do_show(cfg: config.Config) -> None:
    ui.section("Configuration")
    ui.table("Current config (secrets masked)", config.display_rows(cfg))


def do_list(out_dir: Path, archive_dir: Path) -> None:
    ui.section("Local backups")
    man = manifest.read(archive_dir)
    if man:
        arch = man.get("archive", {})
        ui.table("Latest manifest", [
            ("status", "complete" if man.get("complete") else "INCOMPLETE"),
            ("created", man.get("created_utc", "?")),
            ("products", ", ".join(man.get("products", [])) or "?"),
            ("archive", f"{arch.get('name', '?')} "
                        f"({arch.get('size', 0) / (1024 * 1024):.1f} MB)"),
        ])
    else:
        ui.info("No manifest in archive dir (no complete backup yet)")

    files = []
    for d in (out_dir, archive_dir):
        if d.exists():
            for f in sorted(d.glob("*")):
                if f.is_file():
                    files.append((str(f), f"{f.stat().st_size / (1024 * 1024):.1f} MB"))
    ui.table("Files", files) if files else ui.info("No local backup files found")


def do_configure(cfg: config.Config) -> None:
    ui.section("Configure credentials → .env")
    ui.info("Press Enter to keep the current value. Saved to .env (gitignored).")

    cfg.site_jira = ui.prompt("Jira site URL", cfg.site_jira)
    default_conf = cfg.site_confluence or (f"{cfg.site_jira}/wiki" if cfg.site_jira else "")
    cfg.site_confluence = ui.prompt("Confluence site URL (.../wiki)", default_conf)
    cfg.atl_email = ui.prompt("Atlassian account email", cfg.atl_email)
    cfg.atl_token = ui.prompt("Atlassian API token (Confluence)", cfg.atl_token, secret=True)
    cfg.jira_cookies = ui.prompt("Jira cookie blob (paste)", cfg.jira_cookies, secret=True)
    cfg.archive_password = ui.prompt("Archive password (7z; blank = no encryption)",
                                     cfg.archive_password, secret=True)
    cfg.archive_compression = ui.prompt("Compression level 0-9 (0=store, 9=ultra)",
                                        cfg.archive_compression)
    cfg.product_name_template = ui.prompt("Product filename template", cfg.product_name_template)
    cfg.archive_name_template = ui.prompt("Archive (.7z) filename template",
                                          cfg.archive_name_template)

    cfg.storage_provider = ui.prompt("Storage provider (gcs/s3/azure/local)",
                                     cfg.storage_provider)
    cfg.storage_dest = ui.prompt("Storage dest (bucket/container/dir)", cfg.storage_dest)
    if cfg.storage_provider == "gcs":
        cfg.gcp_credentials = ui.prompt("Path to GCP SA key JSON", cfg.gcp_credentials)
    elif cfg.storage_provider == "s3":
        cfg.aws_access_key_id = ui.prompt("AWS access key id", cfg.aws_access_key_id, secret=True)
        cfg.aws_secret_access_key = ui.prompt("AWS secret access key",
                                              cfg.aws_secret_access_key, secret=True)
        cfg.aws_default_region = ui.prompt("AWS region", cfg.aws_default_region)
        cfg.s3_endpoint_url = ui.prompt("S3 endpoint URL (blank for AWS)", cfg.s3_endpoint_url)
    elif cfg.storage_provider == "azure":
        cfg.azure_conn = ui.prompt("Azure connection string", cfg.azure_conn, secret=True)

    cfg.notify_channels = ui.prompt("Notify channels (comma)", cfg.notify_channels)
    if any(h in cfg.notify_channels for h in WEBHOOK_CHANNEL_HINTS):
        cfg.notify_webhook_url = ui.prompt("Notify webhook URL", cfg.notify_webhook_url, secret=True)
    if "email" in cfg.notify_channels:
        cfg.smtp_host = ui.prompt("SMTP host", cfg.smtp_host)
        cfg.smtp_port = ui.prompt("SMTP port", cfg.smtp_port)
        cfg.smtp_user = ui.prompt("SMTP user", cfg.smtp_user)
        cfg.smtp_password = ui.prompt("SMTP password", cfg.smtp_password, secret=True)
        cfg.smtp_from = ui.prompt("From address", cfg.smtp_from)
        cfg.smtp_to = ui.prompt("To address(es)", cfg.smtp_to)

    if ui.confirm("Save to .env?", default=True):
        path = config.save_env(cfg)
        ui.ok(f"Saved {path} (chmod 600 where supported)")
    else:
        ui.warn("Not saved.")


def full_run(cfg: config.Config, out_dir: Path, archive_dir: Path,
             do_notify_step: bool, build_url: str = "", *,
             dry_run: bool = False, skip_existing: bool = False,
             no_encrypt: bool = False) -> int:
    """Backup both → archive → upload → (notify). Returns process exit code."""
    status = "success"
    try:
        errors = do_backup(cfg, ["jira", "confluence"], out_dir, archive_dir,
                           skip_existing=skip_existing, dry_run=dry_run)
        if errors:
            raise RuntimeError(f"backup failed: {', '.join(errors)}")
        do_archive(cfg, out_dir, archive_dir, dry_run=dry_run, no_encrypt=no_encrypt)
        do_upload(cfg, archive_dir, dry_run=dry_run)
    except Exception as exc:
        status = "failure"
        ui.error(str(exc))
    if do_notify_step:
        try:
            do_notify(cfg, status, archive_dir, build_url, dry_run=dry_run)
        except Exception as exc:
            ui.warn(f"notify failed: {exc}")
    return 0 if status == "success" else 1


# ─────────────────────────── interactive menu ───────────────────────────

def _safe(fn, *args, **kwargs) -> None:
    """Run a menu action, keeping the menu alive on any error."""
    try:
        fn(*args, **kwargs)
    except SystemExit as exc:
        ui.error(f"Aborted (exit {exc.code}).")
    except KeyboardInterrupt:
        ui.warn("Cancelled.")
    except Exception as exc:  # menu must survive
        ui.error(str(exc))


def _menu_cleanup(out_dir: Path, archive_dir: Path) -> None:
    raw = ui.prompt("Delete backups older than N days? (blank = only incomplete)", "")
    keep_days = int(raw) if raw.strip().isdigit() else None
    do_cleanup(out_dir, archive_dir, keep_days)


def menu(cfg: config.Config, out_dir: Path, archive_dir: Path) -> None:
    while True:
        ui.section("Atlassian Full-Instance Backup")
        ui.table("", [
            ("Jira",    cfg.site_jira or "(not set)"),
            ("Storage", f"{cfg.storage_provider}:{cfg.storage_dest or '(not set)'}"),
            ("Notify",  cfg.notify_channels or "(none)"),
        ])
        print("  1) Backup Jira          7) Validate backup")
        print("  2) Backup Confluence    8) Cleanup backups")
        print("  3) Backup both          9) Test connections")
        print("  4) Full run            10) Configure credentials")
        print("  5) Archive ./out       11) Show configuration")
        print("  6) Upload ./archive    12) List local backups")
        print("  0) Exit")
        choice = ui.prompt("Select").strip()

        if choice == "1":
            _safe(do_backup, cfg, ["jira"], out_dir, archive_dir)
        elif choice == "2":
            _safe(do_backup, cfg, ["confluence"], out_dir, archive_dir)
        elif choice == "3":
            _safe(do_backup, cfg, ["jira", "confluence"], out_dir, archive_dir)
        elif choice == "4":
            _safe(full_run, cfg, out_dir, archive_dir, True)
        elif choice == "5":
            _safe(do_archive, cfg, out_dir, archive_dir)
        elif choice == "6":
            _safe(do_upload, cfg, archive_dir)
        elif choice == "7":
            _safe(do_validate, archive_dir)
        elif choice == "8":
            _safe(_menu_cleanup, out_dir, archive_dir)
        elif choice == "9":
            _safe(do_test, cfg)
        elif choice == "10":
            _safe(do_configure, cfg)
        elif choice == "11":
            _safe(do_show, cfg)
        elif choice == "12":
            _safe(do_list, out_dir, archive_dir)
        elif choice in ("0", "q", "exit", "quit"):
            return
        else:
            ui.warn("Unknown choice.")


# ─────────────────────────── CLI ───────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Atlassian full-instance backup (menu + CLI)")
    p.add_argument("--backup", metavar="LIST",
                   help="Comma list: jira,confluence (or 'all')")
    p.add_argument("--archive", action="store_true", help="Archive ./out into .7z")
    p.add_argument("--upload", action="store_true", help="Upload ./archive to storage")
    p.add_argument("--notify", action="store_true", help="Send notifications")
    p.add_argument("--all", action="store_true",
                   help="Full run: backup both -> archive -> upload -> notify")
    p.add_argument("--validate", action="store_true",
                   help="Verify the archive against its manifest (sha256)")
    p.add_argument("--cleanup", action="store_true",
                   help="Remove incomplete (and, with --keep-days, old) local backups")
    p.add_argument("--keep-days", type=int, default=None,
                   help="With --cleanup: also delete backups older than N days")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview steps without API calls / archiving / uploading")
    p.add_argument("--skip-existing", action="store_true",
                   help="Skip a product that already has a complete backup today")
    p.add_argument("--compression", type=int, choices=range(0, 10), metavar="0-9",
                   default=None, help="7z compression level 0-9 (overrides config)")
    p.add_argument("--no-encrypt", action="store_true",
                   help="Create an unencrypted archive (ignore the archive password)")
    p.add_argument("--test-connection", action="store_true", help="Test Jira+Confluence auth")
    p.add_argument("--show-config", action="store_true", help="Print config (secrets masked)")
    p.add_argument("--configure", action="store_true", help="Guided .env setup")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Backup download dir")
    p.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE, help="Archive dir")
    p.add_argument("--build-url", default="", help="Build URL for notifications")
    p.add_argument("--env-file", type=Path, default=None, help="Path to .env (default ./.env)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config.load(args.env_file)
    if args.compression is not None:
        cfg.archive_compression = str(args.compression)

    actionable = (args.backup or args.archive or args.upload or args.notify or
                  args.all or args.validate or args.cleanup or args.test_connection or
                  args.show_config or args.configure)
    if not actionable:
        menu(cfg, args.out, args.archive_dir)        # interactive
        return 0

    if args.configure:
        do_configure(cfg)
        return 0
    if args.show_config:
        do_show(cfg)
        return 0
    if args.test_connection:
        return 0 if do_test(cfg) else 1
    if args.validate:
        return 0 if do_validate(args.archive_dir) else 1
    if args.cleanup:
        do_cleanup(args.out, args.archive_dir, args.keep_days)
        return 0
    if args.all:
        return full_run(cfg, args.out, args.archive_dir, do_notify_step=True,
                        build_url=args.build_url, dry_run=args.dry_run,
                        skip_existing=args.skip_existing, no_encrypt=args.no_encrypt)

    # Granular step composition for pipelines.
    status = "success"
    try:
        if args.backup:
            products = (["jira", "confluence"] if args.backup.strip() == "all"
                        else [x.strip() for x in args.backup.split(",") if x.strip()])
            errors = do_backup(cfg, products, args.out, args.archive_dir,
                               skip_existing=args.skip_existing, dry_run=args.dry_run)
            if errors:
                raise RuntimeError(f"backup failed: {', '.join(errors)}")
        if args.archive:
            do_archive(cfg, args.out, args.archive_dir, dry_run=args.dry_run,
                       no_encrypt=args.no_encrypt)
        if args.upload:
            do_upload(cfg, args.archive_dir, dry_run=args.dry_run)
    except Exception as exc:
        status = "failure"
        ui.error(str(exc))
    if args.notify:
        do_notify(cfg, status, args.archive_dir, args.build_url, dry_run=args.dry_run)
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
