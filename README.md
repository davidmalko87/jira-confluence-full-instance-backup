# Jira & Confluence Full-Instance Backup

[![CI](https://github.com/davidmalko87/jira-confluence-full-instance-backup/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/davidmalko87/jira-confluence-full-instance-backup/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/jira-confluence-full-instance-backup.svg?logo=pypi&logoColor=white)](https://pypi.org/project/jira-confluence-full-instance-backup/)
[![PyPI downloads](https://img.shields.io/pypi/dm/jira-confluence-full-instance-backup.svg)](https://pypi.org/project/jira-confluence-full-instance-backup/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/jira-confluence-full-instance-backup.svg?logo=python&logoColor=white)](https://pypi.org/project/jira-confluence-full-instance-backup/)
[![Jira Cloud](https://img.shields.io/badge/Jira-Cloud-0052CC.svg?logo=jira&logoColor=white)](https://www.atlassian.com/software/jira)
[![Confluence Cloud](https://img.shields.io/badge/Confluence-Cloud-172B4D.svg?logo=confluence&logoColor=white)](https://www.atlassian.com/software/confluence)
[![Storage](https://img.shields.io/badge/storage-GCS%20%7C%20S3%20%7C%20Azure%20%7C%20local-success.svg)](#storage-backends)
[![Notify](https://img.shields.io/badge/notify-Chat%20%7C%20Slack%20%7C%20Teams%20%7C%20email%20%7C%20webhook-success.svg)](#notification-channels)
[![Last commit](https://img.shields.io/github/last-commit/davidmalko87/jira-confluence-full-instance-backup.svg)](https://github.com/davidmalko87/jira-confluence-full-instance-backup/commits/master)

Automated **full-instance backup** of **Jira Cloud** and **Confluence Cloud** for
the Atlassian **Standard plan**. Run it by hand from an interactive menu, or
unattended from Jenkins/cron. Backups are encrypted and shipped to **the cloud
of your choice** — Google Cloud Storage, AWS S3 (and S3-compatible stores),
Azure Blob, or a local/mounted directory — with notifications to **any channel**
you use: Slack, Microsoft Teams, Discord, Google Chat, email, or a generic
webhook.

---

## Why?

On **March 30, 2026**, Atlassian [deprecated the Backup Manager API](https://community.atlassian.com/forums/Jira-questions/Backup-Manager-API-deprecation-is-there-going-to-be-a/qaq-p/3120079) for Jira Cloud. Direct API-token calls to the backup endpoint now return:

```
HTTP 403
{"error":"This feature is only accessible from the UI."}
```

The replacement [v2 Backup & Restore API](https://developer.atlassian.com/cloud/admin/backup/) is Premium/Enterprise only, leaving Standard-plan customers with no automation path for full-instance backup — only the manual UI button. This tool restores that automation by **replaying the browser UI session** for Jira, while Confluence uses the OBM REST API (which still accepts API tokens). Both flow into one pipeline that archives, encrypts, uploads, and notifies.

For per-project Jira backup/restore, see the sibling project [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore).

---

## Features

| Feature | Description |
|---|---|
| **Full-instance backup** | Jira (all projects, attachments, avatars, logos) + Confluence (all spaces, attachments) in one run |
| **Run anywhere** | Interactive **menu** for VMs/manual use **and** **CLI flags** for Jenkins/cron — same codebase |
| **Pluggable storage** | **GCS · AWS S3 / S3-compatible (R2, B2, MinIO, Spaces) · Azure Blob · local** — pick one flag; only that SDK is needed |
| **Pluggable notifications** | **Slack · Teams · Discord · Google Chat · email (SMTP) · generic webhook** — any combination, no extra deps |
| **Optional encryption** | 7-Zip AES-256 with encrypted headers — on by default, switch off with `--no-encrypt` |
| **Configurable compression** | `0` (store) … `9` (ultra) |
| **Custom filenames** | Name templates: `{product} {site} {date} {time} {datetime} {timestamp}` |
| **Integrity & housekeeping** | `manifest.json` with sha256 + `--validate`, `--cleanup`, `--skip-existing`, `--dry-run` |
| **Cooldown-aware** | Atlassian's 48h throttle (HTTP 412) is detected and skipped cleanly — no false failures |
| **Connection test** | Validates Jira cookies + Confluence token, warns when the Jira session is near expiry |

---

## Install

```bash
pip install jira-confluence-full-instance-backup            # core (requests)
# add the storage backend you use:
pip install "jira-confluence-full-instance-backup[s3]"      # or [gcs] / [azure]
# optional nicer interactive output (progress bars, color):
pip install "jira-confluence-full-instance-backup[ui]"
# everything:
pip install "jira-confluence-full-instance-backup[all]"
```

Or from source:

```bash
git clone https://github.com/davidmalko87/jira-confluence-full-instance-backup.git
cd jira-confluence-full-instance-backup
pip install -r requirements.txt          # + requirements-<provider>.txt as needed
```

Requirements: Python 3.10+, and `7z` on PATH (`apt install p7zip-full`, or set `SEVEN_ZIP_PATH`).

---

## Quick Start

### 1. Configure

```bash
cp .env.example .env      # fill in real values — .env is gitignored
```

Or use the guided menu (writes `.env` for you): `jira-confluence-backup` → **Configure credentials**.

### 2. Run — interactive menu

```bash
jira-confluence-backup            # or: python main.py   /   python -m backup
```

```
=== Atlassian Full-Instance Backup ===
  Jira     https://<your-site>.atlassian.net
  Storage  s3:my-backups
  Notify   slack

  1) Backup Jira          7) Validate backup
  2) Backup Confluence    8) Cleanup backups
  3) Backup both          9) Test connections
  4) Full run            10) Configure credentials
  5) Archive ./out       11) Show configuration
  6) Upload ./archive    12) List local backups
  0) Exit
```

### 3. Run — CLI (automation)

```bash
jira-confluence-backup --all                              # backup both -> archive -> upload -> notify
jira-confluence-backup --all --dry-run                    # preview only, no API calls / no cooldown burn
jira-confluence-backup --backup jira,confluence --archive --upload --notify
jira-confluence-backup --validate                         # check the archive against its manifest
jira-confluence-backup --cleanup --keep-days 28           # prune incomplete + old local backups
jira-confluence-backup --test-connection                  # exit 0 if both auth paths are OK
```

> Output is plain ASCII (`[INFO]/[OK]`) by default — safe on any console, including legacy Windows. Install the `ui` extra for colored output and progress bars.

---

## How It Works

```
Setup  ->  Jira  ->  Confluence  ->  Archive  ->  Upload          ->  Notify
(venv)    (cookies)  (API token)    (7z, opt.    (<provider>://      (your
                                     AES-256)     <dest>/Y/M/D/)      channels)
```

Stages are independent: a Jira cookie expiry does not stop the Confluence stage.

### Auth model

| Product | Endpoint | Auth | Why |
|---|---|---|---|
| Jira | `/rest/backup/1/export/runbackup` | **Session cookies + UI headers** | Atlassian gates this endpoint to UI sessions only — API tokens return 403 |
| Confluence | `/wiki/rest/obm/1.0/runbackup` | **Basic** (email + API token) | OBM never received the UI-only lockdown |

> **Do not replace the Jira side with an API token** — it is gated to browser
> sessions and returns `403 "This feature is only accessible from the UI."`.
> One dedicated Atlassian **admin account** supplies both: its API token (for
> Confluence) and its browser session cookies (for Jira).

---

## Storage backends

Set `STORAGE_PROVIDER` + `STORAGE_DEST` (or `--provider` / `--dest`). Only the chosen SDK is imported; a missing one prints a `pip install` hint.

| Provider | `STORAGE_DEST` | Optional SDK | Credentials |
|---|---|---|---|
| `gcs` | bucket | `requirements-gcs.txt` | `GOOGLE_APPLICATION_CREDENTIALS` (SA JSON) |
| `s3` | bucket | `requirements-s3.txt` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` |
| `azure` | container | `requirements-azure.txt` | `AZURE_STORAGE_CONNECTION_STRING` |
| `local` | directory | *(none)* | *(none)* |

**S3-compatible stores** (Cloudflare R2, Backblaze B2, MinIO, DigitalOcean Spaces): use `s3` plus `S3_ENDPOINT_URL`. Objects are written to `<dest>/YYYY/MM/DD/`. Retention is the bucket's job (set a lifecycle rule); use a **write-only** identity where possible.

---

## Notification channels

`NOTIFY_CHANNELS` is a comma list — pick any. One report is built and rendered per channel; a failed channel is logged but never blocks the rest.

| Channel | Needs | Notes |
|---|---|---|
| `slack` / `discord` / `teams` / `google-chat` | `NOTIFY_WEBHOOK_URL` | platform-specific incoming webhook |
| `email` | `SMTP_*` | stdlib SMTP; port 465 → SSL, else STARTTLS |
| `webhook` | `NOTIFY_WEBHOOK_URL` | raw JSON POST (PagerDuty / Opsgenie / your API) |

---

## Archiving: encryption, compression, names

- **Encryption** (default on): 7-Zip AES-256 with encrypted headers, password from `ARCHIVE_PASSWORD`. Turn it off with `--no-encrypt` or by leaving the password blank.
- **Compression**: `ARCHIVE_COMPRESSION` / `--compression` `0`–`9`.
- **Names**: `PRODUCT_NAME_TEMPLATE` (the per-product `.zip`) and `ARCHIVE_NAME_TEMPLATE` (the `.7z`). Tokens: `{product} {site} {date} {time} {datetime} {timestamp} {year} {month} {day}`. Defaults: `{product}-{date}` and `atlassian-backup-{date}`.

## Integrity & housekeeping

Each successful run writes a `manifest.json` (timestamp, products, per-file + archive **sha256**, `complete: true`, `encrypted`) next to the archive and uploads it too.

- `--validate` — re-checksum the local archive against the manifest.
- `--cleanup [--keep-days N]` — remove incomplete backups (no manifest) and, optionally, ones older than N days.
- `--skip-existing` — skip a product already backed up today.
- `--dry-run` — preview any flow without API calls, archiving, or uploads.

---

## Jenkins

The `Jenkinsfile` runs a weekly job (cron) and is driven by environment variables:

```groovy
environment {
    SITE_JIRA        = 'https://<YOUR_SITE>.atlassian.net'
    SITE_CONFLUENCE  = 'https://<YOUR_SITE>.atlassian.net/wiki'
    STORAGE_PROVIDER = 'gcs'            // gcs | s3 | azure | local
    STORAGE_DEST     = '<YOUR_BUCKET>'
    NOTIFY_CHANNELS  = 'slack'         // any comma list
}
```

It installs the matching provider SDK and binds **only** the credentials your config needs from the Jenkins Credentials store (`jira-cookies`, `atlassian-email`/`atlassian-api-token`, `archive-password`, the storage credential, and `notify-webhook-url` / `smtp-*`). No secrets live in the repo.

---

## Cookie Refresh Procedure

The Jira `tenant.session.token` JWT expires roughly every 30 days. When it does, the Jira stage exits with code 2 (`Cookie auth rejected — cookies likely expired`). Refresh takes ~60 seconds:

1. Log into Atlassian as the backup admin account.
2. Open `https://<your-site>.atlassian.net/secure/admin/CloudExport.jspa`.
3. **F12 → Application → Cookies** and copy these five: `tenant.session.token`, `atlassian.xsrf.token`, `JSESSIONID`, `AWSALB`, `AWSALBCORS`.
4. Assemble as one semicolon-separated string and update it where it's stored (`JIRA_COOKIES` in `.env`, or the `jira-cookies` Jenkins credential).

`Test connections` warns you in advance when the token is within a few days of expiry.

---

## Response Code Semantics

| Code | Meaning | Behavior |
|---|---|---|
| 200 | Backup queued / status returned | Continue polling |
| 403 | Auth rejected (UI-only gate) | Exit 2 — refresh Jira cookies |
| 412 | 48-hour cooldown active | Exit 0 + marker — stays green |
| 400 | Body schema rejected | Investigate body (Atlassian schema change) |
| 406 | Confluence cosmetic error | Ignore — backup actually started |

---

## Configuration Reference

All values come from environment variables, optionally loaded from `.env` (see `.env.example`). In Jenkins they are bound from the Credentials store at runtime — never from a file in the repo.

| Env var | Purpose |
|---|---|
| `SITE_JIRA` / `SITE_CONFLUENCE` | Atlassian base URLs |
| `JIRA_COOKIES` | Browser session cookie blob for Jira |
| `ATL_EMAIL` / `ATL_TOKEN` | Confluence Basic auth |
| `ARCHIVE_PASSWORD` | 7-Zip AES-256 passphrase (blank = unencrypted) |
| `ARCHIVE_COMPRESSION` | 0–9 |
| `PRODUCT_NAME_TEMPLATE` / `ARCHIVE_NAME_TEMPLATE` | Filename templates |
| `STORAGE_PROVIDER` / `STORAGE_DEST` | Backend + bucket/container/dir |
| `S3_ENDPOINT_URL` | S3-compatible endpoint (s3 only) |
| `GOOGLE_APPLICATION_CREDENTIALS` / `AWS_*` / `AZURE_STORAGE_CONNECTION_STRING` | Provider credentials |
| `NOTIFY_CHANNELS` | Comma list of channels |
| `NOTIFY_WEBHOOK_URL` / `SMTP_*` | Notification delivery |

---

## Project Structure

```
jira-confluence-full-instance-backup/
├── main.py                   # Convenience shim (python main.py)
├── Jenkinsfile               # Declarative pipeline (provider/channel driven)
├── pyproject.toml            # Packaging + console script + ruff config
├── .env.example              # Local-testing template (real .env is gitignored)
├── requirements.txt          # Core (requests)
├── requirements-{gcs,s3,azure,ui}.txt   # Optional extras
└── backup/
    ├── cli.py                # Dual-mode entrypoint (menu + CLI)
    ├── jira.py               # Cookie-authenticated Jira backup
    ├── confluence.py         # OBM Basic-auth Confluence backup
    ├── archive.py            # 7-Zip (optional AES-256, configurable level)
    ├── upload.py             # Multi-provider upload (gcs/s3/azure/local)
    ├── notify.py             # Multi-channel notifier
    ├── manifest.py           # manifest.json: completeness + sha256 integrity
    ├── config.py             # Env/.env config + Configure-menu persistence
    ├── naming.py             # Filename templating
    └── ui.py                 # Console UI (rich-optional, ASCII-safe)
```

---

## Known Limitations

These are Atlassian platform constraints, not tool limitations:

- **48h Jira cooldown** between full-instance backups (weekly cadence is fine).
- **Cookie lifetime** ~30 days; monthly manual refresh required.
- **Confluence Filestore retention** ~14 days (the tool downloads immediately, so this affects only the source file).
- **No restore automation** — restoring a full-instance backup is manual via Atlassian's UI; for per-project restore use [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: no secrets in the repo, keep
cloud SDKs optional, ASCII-only console output, and test auth/backup changes
against a non-prod Atlassian instance. **Do not** switch Jira to API-token auth
(see [Auth model](#auth-model)).

## License

MIT — see [LICENSE](LICENSE).

## Related

* [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore) — per-project Jira Cloud backup/restore via REST API.
