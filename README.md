# Jira & Confluence Full-Instance Backup

[![CI](https://github.com/davidmalko87/jira-confluence-full-instance-backup/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/davidmalko87/jira-confluence-full-instance-backup/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/jira-confluence-full-instance-backup.svg?logo=pypi&logoColor=white)](https://pypi.org/project/jira-confluence-full-instance-backup/)
[![PyPI downloads](https://img.shields.io/pypi/dm/jira-confluence-full-instance-backup.svg)](https://pypi.org/project/jira-confluence-full-instance-backup/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/jira-confluence-full-instance-backup.svg?logo=python&logoColor=white)](https://pypi.org/project/jira-confluence-full-instance-backup/)
[![Jira Cloud](https://img.shields.io/badge/Jira-Cloud-0052CC.svg?logo=jira&logoColor=white)](https://www.atlassian.com/software/jira)
[![Confluence Cloud](https://img.shields.io/badge/Confluence-Cloud-172B4D.svg?logo=confluence&logoColor=white)](https://www.atlassian.com/software/confluence)
[![Storage](https://img.shields.io/badge/storage-GCS%20%7C%20S3%20%7C%20Azure%20%7C%20local-success.svg)](#storage-backends)
[![Notify](https://img.shields.io/badge/notify-Chat%20%7C%20Slack%20%7C%20Teams%20%7C%20email%20%7C%20webhook-success.svg)](#notification-channels)
[![Restore: round-trip verified](https://img.shields.io/badge/restore-round--trip%20verified-brightgreen.svg)](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/docs/RESTORE.md)
[![Last commit](https://img.shields.io/github/last-commit/davidmalko87/jira-confluence-full-instance-backup.svg)](https://github.com/davidmalko87/jira-confluence-full-instance-backup/commits/master)

Automated **full-instance backup** of **Jira Cloud** and **Confluence Cloud** for
the Atlassian **Standard plan**. Run it by hand from an interactive menu, or
unattended from Jenkins/cron. Backups are packed as .7z (AES-256 encrypted when
you set `ARCHIVE_PASSWORD`) and shipped to **the cloud of your choice** — Google Cloud Storage, AWS S3 (and S3-compatible stores),
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
| **Optional encryption** | `.7z` **AES-256** with encrypted headers (filenames hidden) whenever `ARCHIVE_PASSWORD` is set — blank (the default) = unencrypted; `--no-encrypt` forces a plain archive |
| **Pure-Python archiving** | `.7z` via **py7zr** — no 7-Zip binary, so it runs in a bare `python:3.x` container |
| **Configurable compression** | `0` (store) … `9` (ultra) |
| **Custom filenames** | Name templates: `{product} {site} {date} {time} {datetime} {timestamp}` |
| **Integrity & housekeeping** | A sha256 manifest per archive + `--validate`, `--cleanup`, `--skip-existing`, `--dry-run` |
| **Cooldown-aware** | Atlassian's 48h throttle (HTTP 412) is detected — by default the most recent existing backup is downloaded instead; no false failures |
| **Connection test** | Validates Jira cookies, Confluence token and storage write access, and shows how many days the Jira session token has left |

---

## Install

**Via PyPI (recommended)** — provides the `jira-confluence-backup` command:

```bash
pip install jira-confluence-full-instance-backup                # core (requests, py7zr)
pip install "jira-confluence-full-instance-backup[gcs]"         # optional: Google Cloud Storage SDK
pip install "jira-confluence-full-instance-backup[s3]"          # optional: AWS S3 / S3-compatible SDK (boto3)
pip install "jira-confluence-full-instance-backup[azure]"       # optional: Azure Blob SDK
pip install "jira-confluence-full-instance-backup[ui]"          # optional: colored output + progress bars (rich)
pip install "jira-confluence-full-instance-backup[all]"         # optional: all of the above
```

**Or as an isolated app with [pipx](https://pipx.pypa.io/)** — keeps its dependencies out of your global Python:

```bash
pipx install jira-confluence-full-instance-backup
pipx install "jira-confluence-full-instance-backup[s3]"         # with a storage SDK ([gcs] / [azure] / [all] likewise)
```

**Upgrade:**

```bash
pip install -U jira-confluence-full-instance-backup             # pipx: pipx upgrade jira-confluence-full-instance-backup
```

**Or clone and run from source** (development):

```bash
git clone https://github.com/davidmalko87/jira-confluence-full-instance-backup.git
cd jira-confluence-full-instance-backup
pip install -r requirements.txt          # + requirements-<provider>.txt / requirements-ui.txt as needed
python main.py --help                    # same flags as jira-confluence-backup
```

Requirements: **Python 3.10+ only** — archiving is pure-Python (py7zr), so no 7-Zip binary is needed.

> **Where files live:** everything is relative to the folder you run `jira-confluence-backup` from (pip install or clone alike): `.env` is read from there (or from `--env-file PATH`; `--configure` / `--refresh-cookies` still save `./.env`), downloads go to `./out`, archives + manifests to `./archive` (override with `--out` / `--archive-dir`), and the generated `.groovy` files and a relative `local` `STORAGE_DEST` (e.g. `./backups`) land there too. Nothing is written to your home directory or the install location, and there is no log file — output goes to the console. `out/` and `archive/` are not emptied between runs and `--archive` / `--upload` process every file in them (older archives get re-uploaded under the current date folder), so run scheduled jobs from a dedicated folder (`cd /srv/atlassian-backup && jira-confluence-backup --all`) and empty both once a run has uploaded.

### Running in CI / containers

Backups run in a **bare `python:3.x` container** — no system packages:

- Install just the package with your cloud SDK extra, e.g. `pip install "jira-confluence-full-instance-backup[gcs]"` — or, from a clone, `pip install -r requirements.txt` plus `requirements-<provider>.txt`. **Archiving is pure-Python** (py7zr) — **no 7-Zip binary** required.
- A `'…/.cache/pip' is not writable` warning under a non-root container uid is harmless — pip disables its cache and installs anyway.
- **Disk:** peak workspace ≈ the raw exports **+** their archives — roughly **2× the export size**; size the volume accordingly.
- **CPU:** downloads are network-bound, but TLS and py7zr packing are **CPU-bound**. A hard CPU cap noticeably slows the **Archive** step, and can stretch downloads long enough to trigger mid-stream drops — which the resumable downloader now survives (tunable via `BACKUP_DOWNLOAD_*`, set as real environment variables). If archive time matters, give that stage more CPU or lower `ARCHIVE_COMPRESSION`.

---

## Quick Start

### 1. Configure

Run the guided setup from the folder you will run backups from — it writes `./.env` for you:

```bash
jira-confluence-backup --configure     # same as menu -> 13) Configure credentials
```

It explains every field — including how to obtain the Jira cookie blob — and validates what you paste.

Prefer to edit the file yourself? The `.env.example` template is not part of the PyPI package, so download it as `.env` and fill in real values (in a clone, `cp .env.example .env` does the same; `.env` is gitignored):

```bash
curl -o .env https://raw.githubusercontent.com/davidmalko87/jira-confluence-full-instance-backup/master/.env.example
```

> **Hidden input is intentional.** When entering secrets (API token, cookie blob, passwords),
> nothing is echoed to the screen — the prompt shows `[input hidden — paste, then Enter]`. Paste
> and press Enter; the tool confirms back (e.g. *"captured 5 cookie(s); required present"*) so
> you know it registered, without ever displaying the value. Use **Test connections** to verify.

### 2. Run — interactive menu

```bash
jira-confluence-backup --help     # all flags
jira-confluence-backup            # interactive menu (also: python -m backup); enter 0 to exit
```

From a clone, use `python main.py` in place of `jira-confluence-backup` — the flags are identical.

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

**CLI — full run:**

```bash
jira-confluence-backup --all                                # backup both -> archive -> upload -> notify
jira-confluence-backup --all --dry-run                      # preview only, no API calls / no cooldown burn
jira-confluence-backup --all --env-file /etc/atlassian-backup/.env --out /data/out --archive-dir /data/archive
```

**CLI — individual steps:**

```bash
jira-confluence-backup --backup jira,confluence --archive --upload --notify
jira-confluence-backup --backup jira --download-existing    # fetch the latest existing Jira backup, no new trigger
jira-confluence-backup --archive --compression 9 --no-encrypt
```

**CLI — verify & housekeeping:**

```bash
jira-confluence-backup --test-connection                    # exit 0 only if Jira, Confluence and storage all pass
jira-confluence-backup --validate                           # check the archive(s) against their manifest(s)
jira-confluence-backup --cleanup --keep-days 28             # prune local backups (see Integrity & housekeeping)
```

**CLI — configuration & Jenkins:**

```bash
jira-confluence-backup --configure                          # guided setup, saves ./.env
jira-confluence-backup --show-config                        # print the config, secrets masked
jira-confluence-backup --refresh-cookies                    # paste a fresh cURL -> ./.env + update-jira-cookies.groovy
jira-confluence-backup --export-jenkins                     # write jenkins-setup.groovy (credentials + job)
```

| Modifier | Effect |
|---|---|
| `--dry-run` | Preview the flow without API calls, archiving or uploads |
| `--skip-existing` | Skip a product that already has a complete backup today |
| `--download-existing` | Jira: fetch the latest existing backup instead of triggering one — only with `--backup jira` (ignored by `--all`) |
| `--compression 0-9` / `--no-encrypt` | Override `ARCHIVE_COMPRESSION` / write an unencrypted `.7z` |
| `--keep-days N` | With `--cleanup`: also delete local archive files older than N days |
| `--out DIR` / `--archive-dir DIR` | Download / archive folders (default `./out` / `./archive`) |
| `--env-file PATH` | Read config from `PATH` instead of `./.env` |
| `--build-url URL` | Build link included in notifications |

Modifiers need an action flag (`--all`, `--backup`, `--archive`, `--upload`, `--notify`, `--validate`, `--cleanup`, …) — on their own they open the interactive menu, which needs a terminal (so not under cron).

> Console output uses plain `[INFO]/[OK]` tags (no emoji) by default and never crashes a legacy Windows console; a few messages contain `—` / `→`, which an old code-page console may show garbled. Install the `ui` extra for colored output and progress bars.

---

## How It Works

```
Setup  ->  Jira  ->  Confluence  ->  Archive  ->  Upload          ->  Notify
(venv)    (cookies)  (API token)    (7z, opt.    (<provider>://      (your
                                     AES-256)     <dest>/YYYY/MM/)    channels)
```

Stages are independent, but in Jenkins `FAILURE_POLICY` decides what a Jira failure does: the default `balanced` stops the build on expired cookies (exit 2) before the Confluence stage runs, while `resilient` (or `ON_CREDENTIALS=unstable`) marks the build UNSTABLE and still backs up, archives and uploads Confluence. With `jira-confluence-backup --all` (or `--backup … --archive --upload`) the Confluence backup still runs, but a failed Jira backup currently stops the run before Archive / Upload — run `jira-confluence-backup --archive --upload` afterwards to ship it.

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

Set `STORAGE_PROVIDER` + `STORAGE_DEST` (environment or `.env`; the low-level `python -m backup.upload` module that the Jenkinsfile runs also takes `--provider` / `--dest`). Only the chosen SDK is imported; a missing one prints a `pip install` hint. Install the SDK as a package extra, e.g. `pip install "jira-confluence-full-instance-backup[s3]"`; from a clone, use the matching `requirements-<provider>.txt`.

| Provider | `STORAGE_DEST` | Optional SDK | Credentials |
|---|---|---|---|
| `gcs` | bucket | `[gcs]` extra (clone: `requirements-gcs.txt`) | `GOOGLE_APPLICATION_CREDENTIALS` (SA JSON) |
| `s3` | bucket | `[s3]` extra (clone: `requirements-s3.txt`) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` |
| `azure` | container | `[azure]` extra (clone: `requirements-azure.txt`) | `AZURE_STORAGE_CONNECTION_STRING` |
| `local` | directory | *(none)* | *(none)* |

**S3-compatible stores** (Cloudflare R2, Backblaze B2, MinIO, DigitalOcean Spaces): use `s3` plus `S3_ENDPOINT_URL`. Objects are written to `<dest>/YYYY/MM/` by default (`STORAGE_LAYOUT`: `year` | `year-month` | `year-month-day` | `flat`). Retention is the bucket's job (set a lifecycle rule); use a **write-only** identity where possible.

---

## Notification channels

`NOTIFY_CHANNELS` is a comma list — pick any. One report is built and rendered per channel; a failed channel is logged but never blocks the rest.

| Channel | Needs | Notes |
|---|---|---|
| `slack` / `discord` / `teams` / `google-chat` | `NOTIFY_WEBHOOK_URL` | platform-specific incoming webhook |
| `email` | `SMTP_*` | stdlib SMTP; port 465 → SSL, else STARTTLS |
| `webhook` | `NOTIFY_WEBHOOK_URL` | raw JSON POST (PagerDuty / Opsgenie / your API) |

> **Email tip:** use your provider's real SMTP host (e.g. `smtp.gmail.com`, `smtp.office365.com`) — a wrong host shows up as a connection timeout — and an **App Password** for Gmail or MFA-enabled Microsoft 365. Settings table + fixes in [TROUBLESHOOTING](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/docs/TROUBLESHOOTING.md).

---

## Archiving: encryption, compression, names

- **Encryption** (on when `ARCHIVE_PASSWORD` is set): 7-Zip AES-256 with encrypted headers. The password is blank by default, which gives an unencrypted archive — set one (Configure prompts for it); `--no-encrypt` forces a plain archive even when a password is set.
- **Compression**: `ARCHIVE_COMPRESSION` / `--compression` `0`–`9`.
- **Names**: `PRODUCT_NAME_TEMPLATE` names each product file — the downloaded `.zip` and, in the default per-product mode, its `.7z`; `ARCHIVE_NAME_TEMPLATE` names the single `.7z` and is used only with `ARCHIVE_MODE=combined`. Tokens: `{product} {site} {date} {time} {datetime} {timestamp} {year} {month} {day}`. Defaults: `{product}-{date}` and `atlassian-backup-{date}`. Keep `{product}` in `PRODUCT_NAME_TEMPLATE` — without it Jira and Confluence get the same file name and collide.

## Integrity & housekeeping

Each archive gets a manifest next to it — `<archive-stem>.manifest.json` (e.g. `jira-<date>.manifest.json`) in the default per-product mode, `manifest.json` in combined mode — with the timestamp, products, per-file + archive **sha256**, `complete: true` and `encrypted`; it is uploaded too.

- `--validate` — re-checksum the local archive(s) against their manifest(s).
- `--cleanup [--keep-days N]` — remove `.7z` files in `./archive` that no complete manifest references (failed runs) and, once any complete manifest exists, **every file in `./out`** (including raw exports that were not archived yet); with `--keep-days N`, also files in `./archive` older than N days.
- `--skip-existing` — skip a product already backed up today.
- `--dry-run` — preview any flow without API calls, archiving, or uploads.

---

## Jenkins

The `Jenkinsfile` is **cross-platform** — it runs on both Linux (`sh`) and Windows (`powershell`) agents. The agent needs **Python 3.10+** only — archiving is pure-Python (py7zr), so no 7-Zip binary is required. It runs weekly (`cron('H 2 * * 4')`) and installs only the selected provider's SDK.

> 📖 **Full step-by-step guide (prerequisites, plugins, every credential, troubleshooting): [docs/JENKINS_SETUP.md](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/docs/JENKINS_SETUP.md).** The summary below is the quick version.

### Fast setup — one paste (recommended)

1. Configure locally: `jira-confluence-backup --configure` (or menu → **Configure credentials**; writes `./.env`).
2. Generate the setup script: `jira-confluence-backup --export-jenkins` (or menu → **Export Jenkins setup**). This writes `jenkins-setup.groovy` to the current folder (gitignored in a clone).
3. In Jenkins: **Manage Jenkins → Script Console**, paste the file's contents, **Run**. It creates every credential (with the exact IDs) **and** the `atlassian-full-backup` pipeline job pointing at this repo.
4. Open the job → **Build Now**, then **delete `jenkins-setup.groovy`** (it contains secrets).

> The job uses *Pipeline script from SCM*, so Jenkins reads the `Jenkinsfile` straight from the repo at build time — there is no Jenkinsfile to generate or maintain inside Jenkins, and updates flow automatically from the repo.

### Manual setup

The `Jenkinsfile` has nothing to edit — it reads the non-secret settings from Jenkins **global environment variables** at build time (the fast setup creates them). Set them under **Manage Jenkins → System → Global properties → Environment variables** (storage targets and notification channels can also be overridden per run in **Build with Parameters**):

| Global env var | Example |
|---|---|
| `SITE_JIRA` | `https://<YOUR_SITE>.atlassian.net` |
| `SITE_CONFLUENCE` | `https://<YOUR_SITE>.atlassian.net/wiki` |
| `STORAGE_PROVIDER` | `gcs` (`gcs` \| `s3` \| `azure` \| `local`, or a comma list) |
| `STORAGE_DEST` | `<YOUR_BUCKET>` (for `local`: an absolute path on the agent, outside the job workspace) |
| `NOTIFY_CHANNELS` | `slack` (any comma list) |

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
| **Pin a version** instead of always-latest `master` | `JENKINS_BRANCH` = a tag or commit | `refs/tags/v1.3.2` |

For a **private** mirror, create a Jenkins credential (username + token, or an SSH deploy key) and put its **ID** in `JENKINS_REPO_CREDENTIALS_ID` — the secret stays in Jenkins, never in a file or the URL. No `Jenkinsfile` change is needed, and the export updates the job in place, so changing the source later is just: set the values → re-export → paste. Full walkthrough (including the one-time `git clone` for the offline case and how to update a pinned clone): [docs/JENKINS_SETUP.md → "Use your own repo / run offline / pin a version"](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/docs/JENKINS_SETUP.md#use-your-own-repo--run-offline--pin-a-version-decouple-from-github).

---

## Cookie Refresh Procedure

The Jira `tenant.session.token` JWT expires roughly every 30 days. When it does, Atlassian rejects the backup request with `403 "This feature is only accessible from the UI."` and the Jenkins Jira stage exits with code 2 (`Cookie auth rejected — cookies likely expired`); `jira-confluence-backup` prints the same error and exits 1. (Test connections describes that same 403 body as a UI-only-gate rejection "not a cookie problem" — the fix is identical either way: a fresh Copy as cURL.) Refresh takes ~60 seconds:

1. Log into Atlassian as the backup admin account.
2. Open `https://<your-site>.atlassian.net/secure/admin/CloudExport.jspa`.
3. **F12 → Network**, reload the page, right-click the `CloudExport.jspa` request (or any `/rest/backup/1/export/...` request) → **Copy → Copy as cURL**.
4. Paste the whole cURL into `jira-confluence-backup --refresh-cookies` (or the menu's **Configure credentials**; both extract the cookies and save `./.env` — `--refresh-cookies` also writes `update-jira-cookies.groovy` for Jenkins), or into the `jira-cookies` Jenkins credential / `JIRA_COOKIES` in `.env`.

The cookie blob must contain at least `tenant.session.token` and `atlassian.xsrf.token`. Other cookies such as `JSESSIONID` / `AWSALB` / `AWSALBCORS` are load-balancer/servlet cookies that some instances set and others don't — they're forwarded automatically when present, and not required. Using a real request's "Copy as cURL" (rather than the Application→Cookies list) ensures any that *are* needed come along.

`Test connections` shows how many days the session token has left, and every notification warns when it is within 7 days of expiry.

---

## Response Code Semantics

Exit codes below are those of the backup modules the Jenkinsfile runs (`python -m backup.jira` / `backup.confluence`). The `jira-confluence-backup` console script returns only `0` (success) or `1` (failure), plus `2` for a command-line usage error.

| Code | Meaning | Behavior |
|---|---|---|
| 200 | Backup queued / status returned | Continue polling |
| 403 | Auth rejected (UI-only gate) — usually expired cookies | Exit 2 — refresh Jira cookies (a 403 with any other body exits 1) |
| 412 | 48-hour cooldown active | Default (`JIRA_COOLDOWN_ACTION=download-existing`): download the most recent existing backup instead. If there is none, or the action is `skip`: marker file + exit 3, which the default `balanced` policy marks UNSTABLE (yellow) — not a failure. The console script exits 0 here |
| 400 | Body schema rejected | Investigate body (Atlassian schema change) |
| 406 | Confluence cosmetic error | Ignore — backup actually started |

---

## Configuration Reference

All values come from environment variables, optionally loaded from `./.env` or `--env-file` (see `.env.example`); a real environment variable wins over the same key in `.env`. In Jenkins they are bound from the Credentials store at runtime — never from a file in the repo.

| Env var | Purpose |
|---|---|
| `SITE_JIRA` / `SITE_CONFLUENCE` | Atlassian base URLs |
| `JIRA_COOKIES` | Browser session cookie blob for Jira |
| `ATL_EMAIL` / `ATL_TOKEN` | Confluence Basic auth |
| `ARCHIVE_PASSWORD` | `.7z` AES-256 passphrase (blank = unencrypted) |
| `ARCHIVE_COMPRESSION` / `ARCHIVE_MODE` | compression `0`–`9`; per-product vs combined `.7z` |
| `PRODUCT_NAME_TEMPLATE` / `ARCHIVE_NAME_TEMPLATE` | Filename templates |
| `STORAGE_PROVIDER` / `STORAGE_DEST` | Backend + bucket/container/dir (aligned **comma lists** for multiple targets, e.g. `gcs,s3` + `bucketA,bucketB`) |
| `STORAGE_LAYOUT` | date-folder depth for object keys: `year-month` (default) / `year` / `year-month-day` / `flat` |
| `STORAGE_PREFIX` | optional base prefix before the date folders — read only by `python -m backup.upload` (the Jenkins Upload stage; set it as a Jenkins global env var, the export does not carry it); ignored by `jira-confluence-backup` |
| `BACKUP_CRON` | Jenkins schedule (default `H 2 * * 4`) |
| `POLL_TIMEOUT` | max seconds to wait per backup (default `21600` = 6h); `jira-confluence-backup` currently applies it to Jira only — Confluence waits up to the default there |
| `FAILURE_POLICY` / `JIRA_COOLDOWN_ACTION` / `ON_*` | pipeline behaviour per outcome (balanced / resilient / strict + per-outcome overrides) |
| `BACKUP_DOWNLOAD_*` | resumable-download tunables (max attempts / read timeout / backoff) — set them as real environment variables; `jira-confluence-backup` currently ignores them in `.env` |
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
├── requirements.txt          # Core (requests, py7zr)
├── requirements-{gcs,s3,azure,ui}.txt   # Optional extras
├── CHANGELOG.md              # Release notes
├── CONTRIBUTING.md           # Dev setup, versioning, release steps
├── LICENSE                   # MIT
├── .github/workflows/        # ci.yml (ruff + pytest), publish.yml (PyPI)
├── docs/JENKINS_SETUP.md     # Full Jenkins setup guide
├── docs/RESTORE.md           # How to restore a backup (per product)
├── docs/TROUBLESHOOTING.md   # Common errors, fixes and FAQ
├── tests/                    # pytest suite
└── backup/
    ├── __init__.py           # Package version (__version__)
    ├── __main__.py           # python -m backup
    ├── cli.py                # Dual-mode entrypoint (menu + CLI)
    ├── jira.py               # Cookie-authenticated Jira backup
    ├── confluence.py         # OBM Basic-auth Confluence backup
    ├── transfer.py           # Resumable, retrying downloads (HTTP Range + resume)
    ├── diskspace.py          # Pre-flight free-disk check before downloads
    ├── archive.py            # py7zr .7z (optional AES-256, configurable level)
    ├── upload.py             # Multi-provider upload (gcs/s3/azure/local)
    ├── notify.py             # Multi-channel notifier
    ├── manifest.py           # Manifests: completeness + sha256 integrity
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

Run **Test connections** (menu option 8, or `jira-confluence-backup --test-connection`) first — it pinpoints which of Jira /
Confluence / storage is misconfigured. Common errors and fixes (403 vs the 204
"success", cookie refresh, the 48-hour cooldown, storage permissions, Jenkins)
are in **[docs/TROUBLESHOOTING.md](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/docs/TROUBLESHOOTING.md)**.

## Restoring

Restore is manual (via Atlassian's import UI) and has product-specific paths and
Cloud limitations — notably, a Cloud site with **both** Jira and Confluence can't
do a full Confluence site import and must restore space-by-space. See
**[docs/RESTORE.md](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/docs/RESTORE.md)**.

---

## Contributing

See [CONTRIBUTING.md](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/CONTRIBUTING.md). In short: no secrets in the repo, keep
cloud SDKs optional, ASCII-only console output, and test auth/backup changes
against a non-prod Atlassian instance. **Do not** switch Jira to API-token auth
(see [Auth model](#auth-model)).

## License

MIT — see [LICENSE](https://github.com/davidmalko87/jira-confluence-full-instance-backup/blob/master/LICENSE).

## Related

* [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore) — per-project Jira Cloud backup/restore via REST API.
