# Troubleshooting & FAQ

Run `python main.py` → **9) Test connections** first — it checks Jira, Confluence,
and storage and tells you exactly which one is wrong.

## Jira

| Symptom | Cause | Fix |
|---|---|---|
| `Test connections` → **HTTP 204** | **This is success** — authenticated, just no previous backup task yet | Nothing to do |
| `MISSING required cookie(s)` | The pasted blob lacks `tenant.session.token` / `atlassian.xsrf.token` | Re-grab via **Copy as cURL** (see below) |
| `HTTP 403: ... only accessible from the UI` | Atlassian's UI-only gate didn't recognise the request as browser-originated | Make sure you pasted a real logged-in request's **Copy as cURL** (Network tab), not a hand-built blob |
| `HTTP 403 — likely expired/invalid cookies` | The `tenant.session.token` JWT expired (~30 days) | Refresh the cookie blob (re-do Copy as cURL) |
| Backup stage exits **code 2** | Cookies expired/invalid | Refresh cookies and re-run |
| `412` / `[COOLDOWN]` | Atlassian's 48-hour throttle between full-instance backups | Wait 48h; the build stays green — this is not a failure |

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
| `the gcs/s3/azure SDK isn't installed` | Provider SDK missing | `pip install -r requirements-<provider>.txt` |
| `write failed: 403` | The credential lacks write permission | GCS: grant the SA `roles/storage.objectCreator` on the bucket |
| `write failed: 404` | Bucket/container doesn't exist or wrong name | Create it first; enter just the **name** (no `gs://`, no URL) |
| `Your default credentials were not found` (gcs) | `GOOGLE_APPLICATION_CREDENTIALS` unset or wrong path | Point it at a valid service-account JSON key |

The bucket/container must exist beforehand — this tool uploads into it, it does
not create it. Objects are written to `<dest>/YYYY/MM/DD/`.

## Archive / environment

| Symptom | Cause | Fix |
|---|---|---|
| `7-Zip not found` | `7z` not on PATH | `apt install p7zip-full` (Linux) / install 7-Zip and set `SEVEN_ZIP_PATH` (Windows) |
| `ModuleNotFoundError: requests` | Dependencies not installed | `pip install -r requirements.txt` |
| Garbled symbols / no colors in the menu | `rich` not installed (plain ASCII fallback) | Optional: `pip install -r requirements-ui.txt` |

## Jenkins

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot run program "sh"` on Windows | Old Linux-only Jenkinsfile | Use v0.2.0+ (cross-platform Jenkinsfile) |
| `Could not find credentials entry '...'` | Credential missing or wrong ID | Run **Export Jenkins setup** (option 13) → Script Console, or add the credential with the exact ID |
| Job uses placeholder site/bucket | Non-secret config not set | Re-run the export (it sets Jenkins global env vars), or set them in *Manage Jenkins → System* |

Full setup: [JENKINS_SETUP.md](JENKINS_SETUP.md).

## FAQ

- **Where do backups land?** `<provider>:<dest>/YYYY/MM/DD/` — encrypted `.7z` plus a `manifest.json`.
- **How do I verify a backup?** `python main.py --validate` re-checksums the archive against its manifest.
- **How do I preview without running a real backup?** `python main.py --all --dry-run` (no API calls, no cooldown used).
- **Can I back up to more than one cloud?** Yes — set comma lists, e.g. `STORAGE_PROVIDER=gcs,s3` + `STORAGE_DEST=bucketA,bucketB`.
- **How often can Jira be backed up?** Atlassian enforces a 48-hour cooldown per instance.
- **Exit codes:** `0` success (or graceful skip like cooldown), `1` generic failure, `2` human action needed (refresh cookies / fix credentials).
