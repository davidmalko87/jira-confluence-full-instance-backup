# Troubleshooting & FAQ

Run `jira-confluence-backup --test-connection` (or menu → **8) Test connections**;
from a clone, `python main.py` takes the same flags) first — it checks Jira,
Confluence, and storage and tells you exactly which one is wrong.

## Jira

| Symptom | Cause | Fix |
|---|---|---|
| `Test connections` → **HTTP 204** | **This is success** — authenticated, just no previous backup task yet | Nothing to do |
| `MISSING required cookie(s)` | The pasted blob lacks `tenant.session.token` / `atlassian.xsrf.token` | Re-grab via **Copy as cURL** (see below) |
| `HTTP 403: ... only accessible from the UI` (Test connections) or `Cookie auth rejected — cookies likely expired` (backup stage) | The same 403 body from Atlassian's UI-only gate: most often the session cookies have expired; otherwise the blob didn't come from a real browser request. Test connections labels it "not a cookie problem", the backup stage "cookies likely expired" | Re-grab a fresh **Copy as cURL** from a logged-in request (Network tab), not a hand-built blob, and refresh the cookies |
| `HTTP 403 — likely expired/invalid cookies` (Test connections) or `403 from runbackup: ...` (backup stage, exit 1) | The `tenant.session.token` JWT expired (~30 days) or is invalid | Refresh the cookie blob (re-do Copy as cURL) |
| Jenkins Jira stage exits **code 2** (`jira-confluence-backup`: exit 1) | The UI-only gate rejected the cookies (usually expired) | Refresh cookies and re-run |
| `412` / `[COOLDOWN]` | Atlassian's 48-hour throttle between full-instance backups | By default (`JIRA_COOLDOWN_ACTION=download-existing`) the most recent existing backup is downloaded instead. With none to download (or `skip`), the Jenkins Jira stage exits 3 and the default `balanced` policy marks the build UNSTABLE (yellow) — not a failure; `jira-confluence-backup` exits 0. Wait 48h for a fresh backup |

**Getting the cookie blob (the reliable way):** log in, open
`https://<your-site>.atlassian.net/secure/admin/CloudExport.jspa`, press F12 →
**Network**, reload, click the `CloudExport.jspa` request (or any
`/rest/backup/1/export/...` one) → right-click → **Copy → Copy as cURL (bash)**,
and paste the whole thing into **Configure credentials**. It auto-extracts the
cookies. Don't copy `/gateway/` or `/post-office/` requests — they belong to a
different service.

> Note: not all instances use `JSESSIONID` / `AWSALB` / `AWSALBCORS`. Only
> `tenant.session.token` and `atlassian.xsrf.token` are required; the rest are
> forwarded if present.

## Confluence

| Symptom | Cause | Fix |
|---|---|---|
| `Auth rejected (HTTP 401/403)` | Wrong email or API token | Use a **classic** API token from id.atlassian.com → Security → API tokens, with the matching account email |
| `406` on runbackup | Cosmetic — the backup actually starts | Ignore |

## Storage

| Symptom | Cause | Fix |
|---|---|---|
| `the gcs/s3/azure SDK isn't installed` | Provider SDK missing | `pip install "jira-confluence-full-instance-backup[<provider>]"` (e.g. `[s3]`); from a clone, the `pip install -r requirements-<provider>.txt` the hint names |
| `write failed: 403` | The credential lacks write permission | GCS: grant the SA `roles/storage.objectCreator` on the bucket |
| `write failed: 404` | Bucket/container doesn't exist or wrong name | Create it first; enter just the **name** (no `gs://`, no URL) |
| `Your default credentials were not found` (gcs) | `GOOGLE_APPLICATION_CREDENTIALS` unset or wrong path | Point it at a valid service-account JSON key |

The bucket/container must exist beforehand — this tool uploads into it, it does
not create it. Objects are written to `<dest>/YYYY/MM/` by default (configurable
via `STORAGE_LAYOUT`).

## Notifications (email / Slack / webhook)

| Symptom | Cause | Fix |
|---|---|---|
| Email: `WinError 10060` / `Connection timed out` / `getaddrinfo failed` | `SMTP_HOST` is wrong, or the SMTP port is blocked outbound | Use your provider's **real** SMTP host — `smtp.gmail.com` (not `smtp.google.com`), `smtp.office365.com`, `email-smtp.<region>.amazonaws.com`. Confirm the host:port is reachable from the machine/agent (firewall / egress). |
| Email: `SMTPAuthenticationError` / `Username and Password not accepted` | Using the normal account password where an app-specific one is required | Gmail and MFA-enabled Microsoft 365 need an **App Password**, not your login password — generate one and put it in `SMTP_PASSWORD`. |
| Email: `SSLError` / `wrong version number`, or it hangs on send | Port ↔ encryption mismatch | **465 = implicit SSL** (auto-selected when `SMTP_PORT=465`); **587 = STARTTLS** (`SMTP_STARTTLS=true`). Match the port to the mode. |
| Chat / Slack / Teams / Discord: nothing arrives, build stays green | A notification failure is logged but never fails the build (by design) | Look for `notify failed (non-fatal)` in the log; verify `NOTIFY_WEBHOOK_URL` and that the channel is in `NOTIFY_CHANNELS`. |
| Webhook configured but no message | The channel isn't listed in `NOTIFY_CHANNELS` | The URL fires only for channels you list — add e.g. `google-chat` or `webhook` to `NOTIFY_CHANNELS`. |

**Common SMTP settings**

| Provider | Host | Port | Notes |
|---|---|---|---|
| Gmail / Google Workspace | `smtp.gmail.com` | 465 (SSL) or 587 (STARTTLS) | **App Password** required (Account → Security → App passwords) |
| Microsoft 365 / Outlook | `smtp.office365.com` | 587 (STARTTLS) | App Password if MFA is enabled |
| Amazon SES | `email-smtp.<region>.amazonaws.com` | 587 (STARTTLS) | Use SES **SMTP** credentials, not your AWS keys |

In Jenkins these come from the `smtp-host/from/to/user/password` credentials (set by
the export); locally they're the `SMTP_*` vars in `.env`. A send failure never fails
the build — the pipeline only logs it.

## Archive / environment

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: py7zr` | Core deps not installed (archiving is pure-Python — no 7-Zip binary needed) | `pip install jira-confluence-full-instance-backup` (clone: `pip install -r requirements.txt`) |
| `ModuleNotFoundError: requests` | Dependencies not installed | `pip install jira-confluence-full-instance-backup` (clone: `pip install -r requirements.txt`) |
| Garbled symbols / no colors in the menu | `rich` not installed (plain ASCII fallback) | Optional: `pip install "jira-confluence-full-instance-backup[ui]"` (clone: `pip install -r requirements-ui.txt`) |

## Jenkins

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot run program "sh"` on Windows | Old Linux-only Jenkinsfile | Use v0.2.0+ (cross-platform Jenkinsfile) |
| `Could not find credentials entry '...'` | Credential missing or wrong ID | Run **Export Jenkins setup** (option 15) → Script Console, or add the credential with the exact ID |
| Job uses placeholder site/bucket | Non-secret config not set | Re-run the export (it sets Jenkins global env vars), or set them in *Manage Jenkins → System* |

Full setup: [JENKINS_SETUP.md](JENKINS_SETUP.md).

## FAQ

- **Where do backups land?** `<provider>:<dest>/YYYY/MM/` (configurable via `STORAGE_LAYOUT`) — per-product `.7z` files (`jira-<date>.7z`, `confluence-<date>.7z`) each with a `<stem>.manifest.json`.
- **How do I verify a backup?** `jira-confluence-backup --validate` re-checksums the archive against its manifest.
- **How do I preview without running a real backup?** `jira-confluence-backup --all --dry-run` (no API calls, no cooldown used).
- **Can I back up to more than one cloud?** Yes — set comma lists, e.g. `STORAGE_PROVIDER=gcs,s3` + `STORAGE_DEST=bucketA,bucketB`.
- **How often can Jira be backed up?** Atlassian enforces a 48-hour cooldown per instance.
- **Exit codes:** the backup modules the Jenkinsfile runs return `0` success, `1` generic failure, `2` human action needed (refresh cookies / fix credentials), and (Jira only) `3` cooldown / nothing downloaded. The `jira-confluence-backup` console script returns `0` success (a cooldown skip included) or `1` failure — expired cookies included.
