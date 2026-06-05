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
[![Restore: round-trip verified](https://img.shields.io/badge/restore-round--trip%20verified-brightgreen.svg)](docs/RESTORE.md)
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
| **Resilient downloads** | Large exports **resume** (HTTP `Range`) and retry on mid-stream connection drops — a dropped connection no longer loses the whole file |
| **Run anywhere** | Interactive **menu** for VMs/manual use **and** **CLI flags** for Jenkins/cron — same codebase; the `Jenkinsfile` runs on **Linux and Windows** agents |
| **One-paste Jenkins setup** | Export a Script Console script from your config that creates all credentials + the pipeline job — no manual credential forms |
| **Pluggable storage** | **GCS · AWS S3 / S3-compatible (R2, B2, MinIO, Spaces) · Azure Blob · local** — pick one flag; only that SDK is needed |
| **Pluggable notifications** | **Slack · Teams · Discord · Google Chat · email (SMTP) · generic webhook** — any combination, no extra deps |
| **Optional encryption** | `.7z` **AES-256** with encrypted headers (filenames hidden) — on by default, switch off with `--no-encrypt` |
| **Pure-Python archiving** | `.7z` via **py7zr** — no 7-Zip binary, so it runs in a bare `python:3.x` container |
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

Requirements: **Python 3.10+ only** — archiving is pure-Python (py7zr), so no 7-Zip binary is needed.

### Running in CI / containers

Backups run in a **bare `python:3.x` container** — no system packages:

- Install just `pip install -r requirements.txt` (plus `requirements-<provider>.txt` for your cloud SDK, e.g. `requirements-gcs.txt`). **Archiving is pure-Python** (py7zr) — **no 7-Zip binary** required.
- A `'…/.cache/pip' is not writable` warning under a non-root container uid is harmless — pip disables its cache and installs anyway.
- **Disk:** peak workspace ≈ the raw exports **+** their archives — roughly **2× the export size**; size the volume accordingly.
- **CPU:** downloads are network-bound, but TLS and py7zr packing are **CPU-bound**. A hard CPU cap noticeably slows the **Archive** step, and can stretch downloads long enough to trigger mid-stream drops — which the resumable downloader now survives (`BACKUP_DOWNLOAD_*`). If archive time matters, give that stage more CPU or lower `ARCHIVE_COMPRESSION`.

---

## Quick Start

### 1. Configure

```bash
cp .env.example .env      # fill in real values — .env is gitignored
```

Or use the guided menu (writes `.env` for you): `jira-confluence-backup` → **Configure credentials**.
It explains every field — including how to obtain the Jira cookie blob — and validates what you paste.

> **Hidden input is intentional.** When entering secrets (API token, cookie blob, passwords),
> nothing is echoed to the screen — the prompt shows `[input hidden — paste, then Enter]`. Paste
> and press Enter; the tool confirms back (e.g. *"captured 5 cookie(s); all required present"*) so
> you know it registered, without ever displaying the value. Use **Test connections** to verify.

### 2. Run — interactive menu

```bash
jira-confluence-backup            # or: python main.py   /   python -m backup
```

```
=== Atlassian Full-Instance Backup ===
  Jira     https://<your-site>.atlassian.net
  Storage  s3:my-backups
  Notify   slack

  Backup
     1) Jira          2) Confluence     3) Both
     4) Full run (backup -> archive -> upload -> notify)
     5) Fetch existing Jira backup (no new trigger)
  Pipeline steps
     6) Archive ./out      7) Upload ./archive
  Verify & manage
     8) Test connections   9) Validate backup
    10) Cleanup backups   11) List local backups
  Configuration
    12) Show config       13) Configure credentials
    14) Refresh cookies   15) Export Jenkins setup
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

> **Email tip:** use your provider's real SMTP host (e.g. `smtp.gmail.com`, `smtp.office365.com`) — a wrong host shows up as a connection timeout — and an **App Password** for Gmail or MFA-enabled Microsoft 365. Settings table + fixes in [TROUBLESHOOTING](docs/TROUBLESHOOTING.md).

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

The `Jenkinsfile` is **cross-platform** — it runs on both Linux (`sh`) and Windows (`powershell`) agents. The agent needs **Python 3.10+** only — archiving is pure-Python (py7zr), so no 7-Zip binary is required. It runs weekly (`cron('H 2 * * 4')`) and installs only the selected provider's SDK.

> 📖 **Full step-by-step guide (prerequisites, plugins, every credential, troubleshooting): [docs/JENKINS_SETUP.md](docs/JENKINS_SETUP.md).** The summary below is the quick version.

### Fast setup — one paste (recommended)

1. Configure locally: `python main.py` → **Configure credentials** (writes `.env`).
2. Generate the setup script: `python main.py` → **Export Jenkins setup** (or `python main.py --export-jenkins`). This writes a gitignored `jenkins-setup.groovy`.
3. In Jenkins: **Manage Jenkins → Script Console**, paste the file's contents, **Run**. It creates every credential (with the exact IDs) **and** the `atlassian-full-backup` pipeline job pointing at this repo.
4. Open the job → **Build Now**, then **delete `jenkins-setup.groovy`** (it contains secrets).

> The job uses *Pipeline script from SCM*, so Jenkins reads the `Jenkinsfile` straight from the repo at build time — there is no Jenkinsfile to generate or maintain inside Jenkins, and updates flow automatically from the repo.

### Manual setup

Edit the `Jenkinsfile` `environment` block for your site / provider / channels:

```groovy
environment {
    SITE_JIRA        = 'https://<YOUR_SITE>.atlassian.net'
    SITE_CONFLUENCE  = 'https://<YOUR_SITE>.atlassian.net/wiki'
    STORAGE_PROVIDER = 'gcs'            // gcs | s3 | azure | local
    STORAGE_DEST     = '<YOUR_BUCKET>'
    NOTIFY_CHANNELS  = 'slack'          // any comma list
}
```

Create a **Pipeline** job → *Pipeline script from SCM* → Git → this repo → `*/master` → Script Path `Jenkinsfile`, and add the credentials below (IDs **must match exactly** — the pipeline binds only the ones your config needs):

| Credential ID | Kind | Used when |
|---|---|---|
| `jira-cookies` | Secret text | always (Jira) |
| `atlassian-email`, `atlassian-api-token` | Secret text | always (Confluence) |
| `archive-password` | Secret text | always (may be blank = unencrypted) |
| `gcp-backup-sa-key` | Secret file | `STORAGE_PROVIDER=gcs` |
| `aws-access-key-id`, `aws-secret-access-key` | Secret text | `STORAGE_PROVIDER=s3` |
| `azure-storage-connection-string` | Secret text | `STORAGE_PROVIDER=azure` |
| `notify-webhook-url` | Secret text | chat/webhook channels |
| `smtp-host/from/to/user/password` | Secret text | `email` channel |

No secrets live in the repo — they stay in the Jenkins Credentials store.

### Use your own repo, run offline, or pin a version

By default the job clones this tool from the **public GitHub repo on `master`**, fresh on every build. If GitHub being reachable at build time is a concern — it could be removed, rate-limited, or blocked on a locked-down network — or you simply want to lock to a known version, repoint the job at a source you control. Nothing in the pipeline needs GitHub specifically: `checkout scm` clones whatever remote the job is configured with.

Set these in **Configure → "Jenkins job source"** (or in `.env`) **before** running the export, and the generated `jenkins-setup.groovy` wires them into the job:

| Goal | Setting(s) | Example |
|---|---|---|
| **Mirror to your own GitLab / Bitbucket** (keep it internal) | `JENKINS_REPO_URL` (+ `JENKINS_REPO_CREDENTIALS_ID` if private) | `https://gitlab.yourco/team/atlassian-backup.git` |
| **Download once, reuse offline** — clone to the Jenkins box; no internet at build time, GitHub can vanish | `JENKINS_REPO_URL` = a local `file://` path | `file:///srv/jenkins/atlassian-backup` |
| **Pin a version** instead of always-latest `master` | `JENKINS_BRANCH` = a tag or commit | `refs/tags/v0.14.0` |

For a **private** mirror, create a Jenkins credential (username + token, or an SSH deploy key) and put its **ID** in `JENKINS_REPO_CREDENTIALS_ID` — the secret stays in Jenkins, never in a file or the URL. No `Jenkinsfile` change is needed, and the export updates the job in place, so changing the source later is just: set the values → re-export → paste. Full walkthrough (including the one-time `git clone` for the offline case and how to update a pinned clone): [docs/JENKINS_SETUP.md → "Use your own repo / run offline / pin a version"](docs/JENKINS_SETUP.md).

---

## Cookie Refresh Procedure

The Jira `tenant.session.token` JWT expires roughly every 30 days. When it does, the Jira stage exits with code 2 (`Cookie auth rejected — cookies likely expired`). Refresh takes ~60 seconds:

1. Log into Atlassian as the backup admin account.
2. Open `https://<your-site>.atlassian.net/secure/admin/CloudExport.jspa`.
3. **F12 → Network**, reload the page, right-click the `CloudExport.jspa` request (or any `/rest/backup/1/export/...` request) → **Copy → Copy as cURL**.
4. Paste the whole cURL into the menu's **Configure credentials** (it extracts the cookies), or into the `jira-cookies` Jenkins credential / `JIRA_COOKIES` in `.env`.

The cookie blob must contain at least `tenant.session.token` and `atlassian.xsrf.token`. Other cookies such as `JSESSIONID` / `AWSALB` / `AWSALBCORS` are load-balancer/servlet cookies that some instances set and others don't — they're forwarded automatically when present, and not required. Using a real request's "Copy as cURL" (rather than the Application→Cookies list) ensures any that *are* needed come along.

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
| `ARCHIVE_PASSWORD` | `.7z` AES-256 passphrase (blank = unencrypted) |
| `ARCHIVE_COMPRESSION` / `ARCHIVE_MODE` | compression `0`–`9`; per-product vs combined `.7z` |
| `PRODUCT_NAME_TEMPLATE` / `ARCHIVE_NAME_TEMPLATE` | Filename templates |
| `STORAGE_PROVIDER` / `STORAGE_DEST` | Backend + bucket/container/dir (aligned **comma lists** for multiple targets, e.g. `gcs,s3` + `bucketA,bucketB`) |
| `STORAGE_LAYOUT` / `STORAGE_PREFIX` | date-folder depth for object keys; optional base prefix before it |
| `BACKUP_CRON` | Jenkins schedule (default `H 2 * * 4`) |
| `POLL_TIMEOUT` | max seconds to wait per backup (default `21600` = 6h) |
| `FAILURE_POLICY` / `JIRA_COOLDOWN_ACTION` / `ON_*` | pipeline behaviour per outcome (balanced / resilient / strict + per-outcome overrides) |
| `BACKUP_DOWNLOAD_*` | resumable-download tunables (max attempts / read timeout / backoff) |
| `PYTHON_BIN` | Jenkins agent Python path (blank = auto-detect; set if `python` isn't on the service PATH) |
| `S3_ENDPOINT_URL` | S3-compatible endpoint (s3 only) |
| `GOOGLE_APPLICATION_CREDENTIALS` / `AWS_*` / `AZURE_STORAGE_CONNECTION_STRING` | Provider credentials |
| `NOTIFY_CHANNELS` | Comma list of channels |
| `NOTIFY_WEBHOOK_URL` / `SMTP_*` | Notification delivery |
| `NOTIFY_SUBJECT_TEMPLATE` / `NOTIFY_BODY_TEMPLATE` | custom notification text (placeholders) |

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
├── docs/JENKINS_SETUP.md     # Full Jenkins setup guide
├── docs/RESTORE.md           # How to restore a backup (per product)
└── backup/
    ├── cli.py                # Dual-mode entrypoint (menu + CLI)
    ├── jira.py               # Cookie-authenticated Jira backup
    ├── confluence.py         # OBM Basic-auth Confluence backup
    ├── transfer.py           # Resumable, retrying downloads (HTTP Range + resume)
    ├── diskspace.py          # Pre-flight free-disk check before downloads
    ├── archive.py            # py7zr .7z (optional AES-256, configurable level)
    ├── upload.py             # Multi-provider upload (gcs/s3/azure/local)
    ├── notify.py             # Multi-channel notifier
    ├── manifest.py           # manifest.json: completeness + sha256 integrity
    ├── config.py             # Env/.env config + Configure-menu persistence
    ├── jenkins_export.py     # Generate Script Console Groovy (creds + job)
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

## Troubleshooting

Run **Test connections** (menu option 8) first — it pinpoints which of Jira /
Confluence / storage is misconfigured. Common errors and fixes (403 vs the 204
"success", cookie refresh, the 48-hour cooldown, storage permissions, Jenkins)
are in **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**.

## Restoring

Restore is manual (via Atlassian's import UI) and has product-specific paths and
Cloud limitations — notably, a Cloud site with **both** Jira and Confluence can't
do a full Confluence site import and must restore space-by-space. See
**[docs/RESTORE.md](docs/RESTORE.md)**.

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
