# Jenkins Setup Guide

Step-by-step setup for running this backup pipeline in Jenkins, on **Linux or
Windows** agents. The `Jenkinsfile` is cross-platform (it uses `sh` on Linux and
`powershell` on Windows automatically).

There are two paths:

- **[Fast setup](#fast-setup-one-paste)** — generate a script from your local
  config and paste it once into the Jenkins Script Console. Creates all
  credentials + the job. Recommended.
- **[Manual setup](#manual-setup)** — create the credentials and job by hand.

---

## 1. Prerequisites on the Jenkins agent

The agent that runs the job needs:

| Tool | Why | Linux | Windows |
|---|---|---|---|
| Python 3.10+ | runs the backup modules | `apt install python3 python3-venv python3-pip` | `winget install -e --id Python.Python.3.11` |
| 7-Zip | AES-256 archive | `apt install p7zip-full` | `winget install -e --id 7zip.7zip` |
| Git | checkout the repo | `apt install git` | `winget install -e --id Git.Git` |

On **Windows**, after installing, restart the Jenkins service so it picks up the
new PATH (`Restart-Service Jenkins`), and allow script execution once:
`Set-ExecutionPolicy RemoteSigned -Scope LocalMachine` (as admin). The pipeline
sets `SEVEN_ZIP_PATH` to `C:\Program Files\7-Zip\7z.exe` automatically.

> **`python` not recognized?** The Jenkins **service account** often has a
> different PATH than your user (a per-user Python install isn't visible to it).
> The pipeline auto-detects `python`/`py`, but if neither is on the service PATH,
> set the **`PYTHON_BIN`** env var to the full interpreter path (e.g.
> `C:\Users\<you>\AppData\Local\Programs\Python\Python311\python.exe`) — in
> `main.py` Configure (carried by the export) or *Manage Jenkins → System →
> Global properties → Environment variables*. Alternatively, reinstall Python
> "for all users" + "Add to PATH" and `Restart-Service Jenkins`.

> A cloud provider SDK (`google-cloud-storage`, `boto3`, `azure-storage-blob`)
> is **not** needed on the agent up front — the pipeline `pip install`s the one
> matching `STORAGE_PROVIDER` into a per-build virtualenv.

### Required Jenkins plugins

Manage Jenkins → Plugins → Installed. These ship with the "recommended" install;
confirm they're present (install from *Available* if not):

- Pipeline (`workflow-aggregator`)
- Git
- Credentials + Credentials Binding
- Plain Credentials (provides Secret-text and Secret-file credentials)
- Timestamper
- Workspace Cleanup (`ws-cleanup`)
- **PowerShell** — required for Windows agents

---

## 2. Credentials reference

The pipeline binds **only** the credentials your configuration needs. IDs
**must match exactly** — they are hardcoded in the `Jenkinsfile`.

| Credential ID | Kind | Needed when | What it is / how to get it |
|---|---|---|---|
| `jira-cookies` | Secret text | always | Jira browser session cookies — see [Getting the Jira cookie blob](#getting-the-jira-cookie-blob) |
| `atlassian-email` | Secret text | always | The admin account's email |
| `atlassian-api-token` | Secret text | always | Create at id.atlassian.com → Security → **API tokens** (classic) |
| `archive-password` | Secret text | always | A strong 7-Zip passphrase (may be blank for an unencrypted archive, but the credential must still exist) |
| `gcp-backup-sa-key` | **Secret file** | `STORAGE_PROVIDER=gcs` | The service-account JSON key (see [GCS](#gcs-google-cloud-storage)) |
| `aws-access-key-id` | Secret text | `STORAGE_PROVIDER=s3` | IAM access key id |
| `aws-secret-access-key` | Secret text | `STORAGE_PROVIDER=s3` | IAM secret access key |
| `azure-storage-connection-string` | Secret text | `STORAGE_PROVIDER=azure` | Storage account connection string |
| `notify-webhook-url` | Secret text | chat/webhook channels | Incoming-webhook URL (Slack/Discord/Teams/Google Chat) |
| `smtp-host` / `smtp-from` / `smtp-to` / `smtp-user` / `smtp-password` | Secret text | `email` channel | SMTP server settings |

### Getting the Jira cookie blob

Jira's backup endpoint is **UI-gated** — it needs your logged-in browser session
cookies, not an API token. The blob must contain at least
`tenant.session.token` and `atlassian.xsrf.token` (other cookies like
`JSESSIONID` / `AWSALB` are forwarded if your instance uses them):

1. Log into Atlassian as the backup admin account.
2. Open `https://<YOUR_SITE>.atlassian.net/secure/admin/CloudExport.jspa`.
3. **F12 → Network**, reload the page (Ctrl+R).
4. Click the `CloudExport.jspa` request (or any `/rest/backup/1/export/...` one)
   → right-click → **Copy → Copy as cURL (bash)**.
5. Run the tool locally: `python main.py` → **Configure credentials** → paste the
   whole cURL when prompted (it extracts the cookies and validates them). The
   value it saves to `.env` is what goes into the `jira-cookies` credential.

The `tenant.session.token` JWT expires ~30 days — see [Cookie refresh](#cookie-refresh).

### GCS (Google Cloud Storage)

```bash
gcloud storage buckets create gs://<YOUR_BUCKET> --location=us-central1

# write-only service account (uploads only — cannot read or delete)
gcloud iam service-accounts create atlassian-backups
gcloud storage buckets add-iam-policy-binding gs://<YOUR_BUCKET> \
  --member="serviceAccount:atlassian-backups@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=atlassian-backups@PROJECT_ID.iam.gserviceaccount.com

# 28-day lifecycle delete (aligns with Atlassian's ~30-day restore window)
cat > lifecycle.json <<JSON
{"rule":[{"action":{"type":"Delete"},"condition":{"age":28}}]}
JSON
gcloud storage buckets update gs://<YOUR_BUCKET> --lifecycle-file=lifecycle.json
```

Upload `sa-key.json` as the `gcp-backup-sa-key` **Secret file** credential.

---

## 3. Fast setup (one paste)

This turns your already-working local config into Jenkins credentials + the job.

1. **Configure locally** (on any machine with the tool):
   `python main.py` → **10) Configure credentials** → fill everything in →
   `python main.py` → **9) Test connections** to confirm Jira / Confluence /
   storage all pass.
2. **Generate the setup script**:
   `python main.py` → **13) Export Jenkins setup** (or `python main.py --export-jenkins`).
   This writes a **gitignored** `jenkins-setup.groovy`.
3. **Import into Jenkins**: Manage Jenkins → **Script Console** → paste the file's
   contents → **Run**. It creates every credential (with the exact IDs) **and**
   the `atlassian-full-backup` pipeline job pointing at this repo.
4. **Delete `jenkins-setup.groovy`** — it contains your real secrets.
5. Skip to [First build](#5-first-build--smoke-test).

> The Script Console runs as the Jenkins admin, so no script approval is needed.
> The job uses *Pipeline script from SCM*, so Jenkins reads the `Jenkinsfile`
> from the repo at build time — there is nothing to maintain inside Jenkins.

### Is it safe to run on a production / shared Jenkins?

Yes, with a quick review — the script is short and readable, and every change it
makes is reversible. Before running it on a shared/production controller, know that it:

- **Creates or updates credentials** with the listed IDs (`jira-cookies`, etc.).
  If a credential with the same ID already exists, it is **overwritten** — check
  for ID clashes first.
- **Creates or updates a job** named `atlassian-full-backup` (overwrites one with
  that name if it exists).
- **Sets Jenkins *global* environment variables** (`SITE_JIRA`, `STORAGE_PROVIDER`,
  `NOTIFY_CHANNELS`, `BACKUP_CRON`, …). These apply to **every job on the
  controller** — on a shared controller, confirm none of those names collide with
  other jobs. (On a dedicated backup controller this is a non-issue.)

Recommendations: **read the generated `jenkins-setup.groovy` before running it**
(Script Console executes as admin), prefer a **dedicated controller/agent** for
backups, and **delete the file afterward** (it embeds your secrets). The console
output prints only credential IDs, never values.

---

## 4. Manual setup

### 4a. Add credentials

Manage Jenkins → **Credentials → System → Global credentials → Add Credentials**.
Add the rows from the [credentials table](#2-credentials-reference) that your
configuration needs. Scope = Global; Description = same as the ID.

### 4b. Configure the pipeline environment

The `Jenkinsfile` `environment` block holds the non-secret settings. Edit them
for your deployment (commit to your own branch/fork, or edit in place):

```groovy
environment {
    SITE_JIRA        = 'https://<YOUR_SITE>.atlassian.net'
    SITE_CONFLUENCE  = 'https://<YOUR_SITE>.atlassian.net/wiki'
    STORAGE_PROVIDER = 'gcs'            // gcs | s3 | azure | local
    STORAGE_DEST     = '<YOUR_BUCKET>'  // bucket / container / directory
    S3_ENDPOINT_URL  = ''               // only for R2 / B2 / MinIO / Spaces
    NOTIFY_CHANNELS  = 'google-chat'    // comma list, or empty
    PRODUCT_NAME_TEMPLATE = '{product}-{date}'
    ARCHIVE_NAME_TEMPLATE = 'atlassian-backup-{date}'
    ARCHIVE_COMPRESSION   = '5'
}
```

### 4c. Create the job

New Item → name `atlassian-full-backup` → **Pipeline** → OK. On the config page:

- Discard old builds: Keep 90 (optional)
- Do not allow concurrent builds: ✅
- **Pipeline → Definition: Pipeline script from SCM**
  - SCM: **Git**
  - Repository URL: `https://github.com/davidmalko87/jira-confluence-full-instance-backup.git`
    (or your fork)
  - Credentials: *none* (public repo)
  - Branch Specifier: `*/master`
  - Script Path: `Jenkinsfile`
  - Lightweight checkout: ✅
- Save.

---

## 5. First build & smoke test

Open the job → **Build Now**. Each step is a separate stage you can watch in the
**Stage View** on the job page: Setup → Jira backup → Confluence backup → Archive
→ Upload → Notify. For a live graphical per-stage view, install the **Blue Ocean**
plugin (Manage Jenkins → Plugins). Click a build → **Console Output** for details.

| Outcome | Meaning |
|---|---|
| ✅ all stages green | backup landed in your store under `YYYY/MM/DD/` |
| ⚠️ Jira logs `[COOLDOWN]` / exits 0 with marker | Atlassian's 48-hour throttle — auth worked; retry after 48h |
| ❌ Jira exit code 2 | cookies expired/invalid → [refresh](#cookie-refresh) |
| ❌ Confluence `401/403` | wrong email or API token |
| ❌ Upload `403` | storage credential lacks write permission (GCS: `objectCreator`) |
| ❌ Setup fails on `python`/`venv` | Python not on the Jenkins agent PATH (Windows: restart the service) |
| ❌ Archive fails on `7z` | 7-Zip not installed / `SEVEN_ZIP_PATH` wrong |

> **First run often hits the 48-hour cooldown** if a manual backup was taken
> recently. A `412` cooldown is a *success signal* that auth works — the build
> stays green. Re-run after 48h for a real `.7z`.

---

## 6. Schedule & per-run options

**Schedule (cron):** driven by the `BACKUP_CRON` global env var (default
`H 2 * * 4` = Thursday ~02:00). Set it in `python main.py` → Configure (it's
carried to Jenkins by the export), or in *Manage Jenkins → System → Global
properties → Environment variables*.

**Build with Parameters:** the job exposes provider(s), destination(s), notify
channels, compression, and name templates as build parameters — defaulting to
your configured values. Use **Build with Parameters** to override them for a
one-off run without changing your saved config.

**Multiple storage targets:** set `STORAGE_PROVIDER` and `STORAGE_DEST` to
aligned comma lists, e.g. `gcs,s3` + `my-gcs-bucket,my-s3-bucket` — the archive
uploads to each. The export creates the credentials for every listed provider.

---

## 7. Operations

### Cookie refresh (monthly)

The `tenant.session.token` JWT expires ~30 days. You'll be reminded *before* it
fails: every notification warns when the cookie is within 7 days of expiry.

Fastest refresh (validated):

1. `python main.py` → **Refresh Jira cookies** (or `python main.py --refresh-cookies`).
2. Paste a fresh **Copy as cURL** (see [Getting the Jira cookie blob](#getting-the-jira-cookie-blob)). It's validated (and optionally live-tested) and saved to `.env`.
3. It writes `update-jira-cookies.groovy` — paste it into **Manage Jenkins → Script Console → Run** to update only the `jira-cookies` credential. Delete the file afterward.

Or update it by hand: Manage Jenkins → Credentials → `jira-cookies` → Update.

### Credential ↔ stage map

| Stage | Credentials bound | Common failure |
|---|---|---|
| Setup | none | Python/venv/network |
| Jira backup | `jira-cookies` | exit 2 = refresh cookies |
| Confluence backup | `atlassian-email`, `atlassian-api-token` | 401/403 = wrong token |
| Archive | `archive-password` | 7z missing on agent |
| Upload | storage credential (provider-specific) | 403 = missing write permission |
| Notify | `notify-webhook-url` and/or `smtp-*` | bad webhook/SMTP (non-fatal) |

### Notes

- `cleanWs()` wipes the workspace after each build — **the uploaded archive in
  your object store is the only persistence.** Confirm the Upload stage
  succeeded.
- Secrets never live in the repo; they stay in the Jenkins Credentials store and
  are bound at runtime via `withCredentials`.

---

## Troubleshooting 403 on the Jira stage

If Jira returns `403`, the tool prints the response body. Two cases:

- **"only accessible from the UI"** → Atlassian's UI-only gate rejected the
  request as non-browser. The cookies are fine; the request didn't look
  browser-like enough. Confirm you copied a real logged-in request's cURL.
- **Other 403 / expired** → the session is no longer valid; refresh the cookie
  blob.

Cross-check: run the browser's `Copy as cURL` of `/rest/backup/1/export/lastTaskId`
directly (`curl.exe ...`). If that returns 200 but the pipeline doesn't, it's a
request-shape issue; if even the raw cURL 403s outside the browser, the session
is the problem.
