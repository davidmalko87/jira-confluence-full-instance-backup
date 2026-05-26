# jira-confluence-full-instance-backup

Full-instance backup of Jira Cloud and Confluence Cloud to Google Cloud Storage. Jenkins pipeline that restores the automation removed when Atlassian deprecated the Backup Manager API in March 2026. Replicates UI session auth for Jira, OBM API for Confluence, 7-Zip AES-256 encryption, GCS upload. For Standard plan customers.

## Why?

On **March 30, 2026**, Atlassian [deprecated the Backup Manager API](https://community.atlassian.com/forums/Jira-questions/Backup-Manager-API-deprecation-is-there-going-to-be-a/qaq-p/3120079) for Jira Cloud. Direct API-token calls to `/rest/backup/1/export/runbackup` now return:

```
HTTP 403
{"error":"This feature is only accessible from the UI."}
```

The replacement [v2 Backup and Restore API](https://developer.atlassian.com/cloud/admin/backup/) is Premium/Enterprise only. Standard plan customers were left with no automation path for full-instance backup — only the manual UI button at `/secure/admin/CloudExport.jspa`.

This pipeline restores full-instance backup automation by **replaying the browser UI session** (cookies + UI headers) from Jenkins. Confluence backups use the OBM REST API which still accepts API tokens. Both flow into a single weekly Jenkins job that archives, encrypts, and uploads to Google Cloud Storage.

For per-project Jira backup/restore (a complementary tool for granular recovery), see [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore).

## Features

* **Full-instance backup** — Jira (all projects, attachments, avatars, logos) + Confluence (all spaces, attachments) in one pipeline
* **Dual auth model** — session cookies + UI headers for Jira (gated endpoint), API token Basic auth for Confluence (OBM endpoint)
* **Jenkins pipeline** — declarative `Jenkinsfile`, weekly cron, audit trail via build logs anyone on the team can read
* **48-hour cooldown handling** — Atlassian's per-instance throttle returns HTTP 412; pipeline detects, logs, exits clean (build stays green)
* **AES-256 encryption** — 7-Zip with `-mhe=on` (encrypted headers), strong passphrase from Jenkins Credentials
* **GCS upload** — service-account auth, write-only IAM (`roles/storage.objectCreator`), bucket-scoped
* **Google Chat notifications** — success/failure card with file sizes and direct link to Jenkins build
* **Stages are independent** — Jira cookie expiry does not break the Confluence stage; one product can succeed while the other reports

## Quick Start

### 1. Clone and review

```bash
git clone https://github.com/davidmalko87/jira-confluence-full-instance-backup
cd jira-confluence-full-instance-backup
```

### 2. Provision GCS

```bash
# Bucket
gcloud storage buckets create gs://your-atlassian-backups --location=us-central1

# 28-day lifecycle delete (aligns with Atlassian's 30-day restore cap)
cat > lifecycle.json <<JSON
{"rule":[{"action":{"type":"Delete"},"condition":{"age":28}}]}
JSON
gcloud storage buckets update gs://your-atlassian-backups --lifecycle-file=lifecycle.json

# Write-only service account
gcloud iam service-accounts create atlassian-backups
gcloud storage buckets add-iam-policy-binding gs://your-atlassian-backups \
  --member="serviceAccount:atlassian-backups@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=atlassian-backups@PROJECT_ID.iam.gserviceaccount.com
```

### 3. Configure Jenkins credentials

Under **Manage Jenkins → Credentials → System → Global**:

| ID | Type | Value |
|---|---|---|
| `jira-cookies` | Secret text | Cookie blob from browser DevTools (see [Cookie refresh](#cookie-refresh-procedure)) |
| `atlassian-email` | Secret text | Email associated with API token |
| `atlassian-api-token` | Secret text | [Generate token](https://id.atlassian.com/manage-api-tokens) |
| `archive-password` | Secret text | Strong passphrase for 7-Zip AES-256 |
| `gcp-backup-sa-key` | Secret file | `sa-key.json` from step 2 |
| `chat-webhook` | Secret text | Google Chat space webhook URL |

### 4. Create the Jenkins job

* **New Item → Multibranch Pipeline** → point at this repo
* Pipeline reads the `Jenkinsfile` automatically
* First build triggers manually; subsequent builds run on the cron schedule

### 5. Configure your site URLs

Edit `Jenkinsfile` environment block:

```groovy
environment {
    SITE_JIRA       = 'https://your-domain.atlassian.net'
    SITE_CONFLUENCE = 'https://your-domain.atlassian.net/wiki'
    GCS_BUCKET      = 'your-atlassian-backups'
}
```

## How It Works

### Pipeline flow

```
Jenkins job (cron: Thursday 02:00 UTC)
  └─ Setup            → venv + dependencies
  └─ Jira backup      → cookie auth + UI headers
  └─ Confluence backup → API token Basic auth
  └─ Archive          → 7z AES-256 with -mhe=on
  └─ GCS upload       → gs://<bucket>/YYYY/MM/DD/
  └─ Notify           → Google Chat card (success/failure)
```

### Auth model

| Product | Endpoint | Auth | Why |
|---|---|---|---|
| Jira | `/rest/backup/1/export/runbackup` | Session cookies + UI headers | Atlassian gates this endpoint to UI sessions only — API token returns 403 |
| Confluence | `/wiki/rest/obm/1.0/runbackup` | Basic (email + API token) | OBM never received the UI-only lockdown |

### Jira request contract

The body format matters — `"what":"all"` is rejected by the current schema, booleans are rejected for the same fields. Modern UI sends:

```json
{"cbAttachments": "true", "exportToCloud": "true"}
```

With required headers: `X-Requested-With: XMLHttpRequest`, `Referer: <site>/secure/admin/CloudExport.jspa`, `Origin: <site>`.

## Cookie Refresh Procedure

The `tenant.session.token` JWT inside the cookie blob expires roughly every 30 days. When it does, Jenkins fails with exit code 2 and message `Cookie auth rejected — cookies likely expired`. Refresh takes about 60 seconds:

1. Log into Atlassian in your browser as the admin account driving the backup
2. Open `https://your-domain.atlassian.net/secure/admin/CloudExport.jspa`
3. **F12 → Application → Cookies → `https://your-domain.atlassian.net`**
4. Find and copy values for these five cookies:
   * `tenant.session.token`
   * `atlassian.xsrf.token`
   * `JSESSIONID`
   * `AWSALB`
   * `AWSALBCORS`
5. Assemble into a single semicolon-separated string:
   ```
   tenant.session.token=eyJ...; atlassian.xsrf.token=...; JSESSIONID=...; AWSALB=...; AWSALBCORS=...
   ```
6. **Jenkins → Manage Credentials → `jira-cookies` → Update** with the new string
7. Optionally trigger the job manually to verify

### Alternative: Copy as cURL

In DevTools Network panel, click any captured request to `your-domain.atlassian.net`, **Copy → Copy as cURL**. The `-b '...'` portion is the cookie blob — paste that whole thing into Jenkins. The script filters to the cookies it actually needs.

## Response Code Semantics

| Code | Meaning | Pipeline behavior |
|---|---|---|
| 200 | Backup queued / status returned | Continue to polling |
| 403 | Auth rejected (UI-only gate) | Exit code 2 — cookies expired, refresh needed |
| 412 | 48-hour cooldown active | Exit code 0 + marker file — build stays green |
| 400 | Body schema rejected | Investigate body format — Atlassian schema may have changed |
| 406 | Confluence cosmetic error | Ignore, backup actually started |

## Project Structure

```
jira-confluence-full-instance-backup/
├── Jenkinsfile                   # Declarative pipeline definition
├── CLAUDE.md                     # Project memory for Claude Code
├── requirements.txt              # Python dependencies
│
├── backup/
│   ├── __init__.py
│   ├── jira.py                   # Cookie-authenticated Jira full-instance backup
│   ├── confluence.py             # Basic-auth Confluence backup (OBM)
│   ├── archive.py                # 7-Zip AES-256 wrap
│   ├── gcs_upload.py             # GCS upload (write-only SA)
│   └── notify.py                 # Google Chat webhook
│
└── docs/
    └── screenshots/              # DevTools capture, Jenkins UI references
```

## Requirements

* **Jenkins** — any modern version with declarative pipeline support
* **Build agent** — Linux with Python 3.10+ and `7z` (`apt install p7zip-full`)
* **Atlassian** — Cloud Standard plan or higher, admin account
* **GCP** — bucket + service account with `roles/storage.objectCreator`
* **Python deps** — `requests`, `google-cloud-storage` (see `requirements.txt`)

## Configuration Reference

All sensitive values come from Jenkins Credentials store, bound to env vars at runtime via `withCredentials`. No `.env` file in production. Site URLs and bucket name are hardcoded in `Jenkinsfile` (intended — they rarely change and aren't sensitive).

| Env var | Source | Purpose |
|---|---|---|
| `JIRA_COOKIES` | Jenkins credential `jira-cookies` | Browser session cookies for Jira UI auth |
| `ATL_EMAIL` | Jenkins credential `atlassian-email` | Confluence Basic auth |
| `ATL_TOKEN` | Jenkins credential `atlassian-api-token` | Confluence Basic auth |
| `ARCHIVE_PASSWORD` | Jenkins credential `archive-password` | 7-Zip AES-256 passphrase |
| `GOOGLE_APPLICATION_CREDENTIALS` | Jenkins credential `gcp-backup-sa-key` (Secret file) | Path to GCP SA JSON key |
| `WEBHOOK` | Jenkins credential `chat-webhook` | Google Chat space webhook URL |

## Known Limitations

These are Atlassian platform constraints — not tool limitations:

| Constraint | Notes |
|---|---|
| Jira backup cooldown | 48 hours between full-instance backups. Weekly cadence is well within budget. |
| Confluence Filestore retention | Generated backup file is auto-deleted after 14 days from Atlassian's Filestore. This pipeline downloads immediately after generation, so retention applies only to the source file. |
| Cookie lifetime | `tenant.session.token` JWT expires ~30 days from issue. Monthly manual refresh required. |
| No restore automation | Restoring a full-instance backup is manual via Atlassian's Backup Manager UI. For per-project granular restore on Standard plan, use [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore). |
| Standard plan restore cap | Atlassian Legacy Backup Manager rejects backup files older than 30 days at import. GCS lifecycle policy mirrors this with 28-day deletion. |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Exit code 2, "Required cookies missing" | Cookie blob malformed | Re-paste, verify all 5 cookies present |
| Exit code 2, "Cookie auth rejected" | Cookies expired (~30 days) | Refresh per [Cookie Refresh Procedure](#cookie-refresh-procedure) |
| Jira `412` with cooldown text | 48h cooldown active | Wait, or check if someone triggered manual backup |
| Confluence `406` on runbackup | Cosmetic — backup actually ran | Pipeline continues, no action |
| GCS upload `403` | SA missing `objectCreator` | Re-check IAM binding at bucket level |
| 7z exit code non-zero | Disk space, special chars in password | Check agent disk, escape password if needed |
| Jira POST `400` "Invalid request payload" | Body schema rejected | Likely Atlassian schema change — capture browser body, patch `backup/jira.py` |

## Contributing

Pull requests welcome. Before changing auth code, **read `CLAUDE.md`** — it captures empirical findings (which auth methods work, which body formats are rejected, response code semantics) that prevent re-deriving the same conclusions. The Jira auth gate is real and absolute; do not propose replacing cookie auth with API tokens.

Test changes against a non-production Atlassian instance first. Atlassian's error responses are inconsistent (400 sometimes surfaces as 403) — empirical testing beats reading docs.

Exit code convention:
* `0` — success (or graceful skip like cooldown)
* `1` — generic failure
* `2` — human action needed (refresh cookies, fix credentials)

## License

MIT — see [LICENSE](LICENSE).

## Related Projects

* [`jira-project-backup-restore`](https://github.com/davidmalko87/jira-project-backup-restore) — Per-project Jira Cloud backup/restore via REST API v2/v3. Complementary to this pipeline for granular recovery scenarios beyond the 30-day Backup Manager restore cap.
