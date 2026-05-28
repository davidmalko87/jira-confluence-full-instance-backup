# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.14.1] - 2026-05-28

### Added
- **Docs: notification / email (SMTP) setup & troubleshooting.** Added a "Notifications" section to `docs/TROUBLESHOOTING.md` covering the common email failures — a wrong `SMTP_HOST` surfacing as a connection timeout (e.g. `smtp.google.com` instead of `smtp.gmail.com`), App Password requirements for Gmail / MFA-enabled Microsoft 365, and matching the port to the encryption mode (465 = implicit SSL, 587 = STARTTLS) — plus a common-provider settings table (Gmail / Microsoft 365 / Amazon SES). Cross-linked from `.env.example` and the README notification-channels table.

---

## [0.14.0] - 2026-05-28

### Added
- **Configurable Jenkins job source — decouple the build from GitHub.** The pipeline job no longer has to clone the public GitHub repo on every build. Three new settings — **`JENKINS_REPO_URL`**, **`JENKINS_BRANCH`**, and **`JENKINS_REPO_CREDENTIALS_ID`** — let the generated `jenkins-setup.groovy` point the job at any Git source: a **private mirror** (GitLab/Bitbucket, with a Jenkins credential ID for auth so the secret stays in Jenkins), a local **`file://` clone** (clone once, reuse offline — no internet or GitHub dependency at build time), or a **pinned tag / commit** (`refs/tags/v0.14.0`) instead of always-latest `master`. Surfaced in `Configure → "Jenkins job source"` (advanced; blank = the built-in GitHub repo), and documented in the README, `.env.example`, and the Jenkins setup guide. No `Jenkinsfile` change — `checkout scm` already clones whatever remote the job is configured with.

---

## [0.13.0] - 2026-05-27

### Added
- **Customizable notification text + richer variables.** Notifications now carry **products**, **date**, item **count**, and **total size** (pulled from the manifests) alongside the existing status / timestamp / archive list / build URL / warnings — surfaced in every channel. Two new optional settings let you reword messages without editing code: **`NOTIFY_SUBJECT_TEMPLATE`** (email subject) and **`NOTIFY_BODY_TEMPLATE`** (Slack / webhook / email body), using `{status} {icon} {date} {time} {products} {count} {size} {archives} {build_url} {warnings}` placeholders. The card channels (Google Chat / Discord / Teams) gain enriched **Products** and per-archive **count + size** fields. The webhook JSON now includes `date`, `products`, `count`, and `total_size_mb`. Carried to Jenkins as global env vars by the export; documented in `.env.example`.

---

## [0.12.1] - 2026-05-27

### Added
- **Docs: "Changing config, credentials, or notifications later (no teardown)"** — documents that the generated `jenkins-setup.groovy` is idempotent (credentials updated-by-ID, global env overwritten, the job updated **in place** with history preserved), so changing creds / switching notification channels / etc. never requires deleting or recreating the job. Includes the lighter paths (`--refresh-cookies`, single-credential UI edit, per-run Build-with-Parameters) and a worked email→webhook example.
- **Docs: "How your code reaches the agent"** — clarifies that the repo is cloned fresh into the agent workspace on **every** build (not just the first), the workspace is wiped by `cleanWs()` afterward (only the uploaded archive persists), and the setup Groovy runs once on the controller via Script Console (never stored on the agent).

---

## [0.12.0] - 2026-05-27

### Added
- **Disk-space pre-flight check.** Right after a download's size is known (and before any bytes are written), the Jira and Confluence stages check free space on the output directory: a download that **definitely won't fit fails fast** with a clear message instead of filling the disk and leaving a truncated backup, and a **tight** situation (below `MIN_FREE_DISK_MB`, default 500, or under 2× the incoming size) logs a warning. A stat failure is ignored rather than blocking the backup.

---

## [0.11.2] - 2026-05-27

### Changed
- **`docs/RESTORE.md`: Jira restore verified + corrected.** A backup produced by this tool was confirmed to import cleanly into Jira Cloud (Atlassian's importer validated it — "everything looks good" — read the correct source/timestamp, and ran to completion). Corrected the earlier note that wrongly implied importing over an existing site is restricted: Jira's Cloud import **overwrites** existing data (users/groups merge), and works into a populated site. Added the large-instance data/media split guidance (`.xml` ≤ 20 GB) and the Free-plan user cap.

---

## [0.11.1] - 2026-05-27

### Fixed
- **Confluence export check no longer false-warns.** The v0.11.0 check looked for `entities.xml` — that's the Confluence *Server/DC* XML-backup format. Confluence *Cloud* `Site_Backup.zip` is a multi-file ZIP that doesn't use a top-level `entities.xml`, so the check now treats a valid, non-corrupt, multi-file ZIP as a good Confluence backup (Jira still verifies `entities.xml`/`activeobjects.xml`). The "not a ZIP / corrupt / empty" hard-fail (the real garbage guard) is unchanged.

### Added
- **`docs/RESTORE.md`** — how to restore each product, including the important Atlassian limitation that a Cloud site with **both** Jira and Confluence can't do a full Confluence site import (you import space-by-space), and that these are full-instance DR/migration artifacts. Linked from the README.

---

## [0.11.0] - 2026-05-27

### Added
- **Downloaded backups are verified before they're stored** — `manifest.verify_export()` opens each freshly-downloaded export and confirms it's a real Atlassian backup ZIP (valid, non-empty, no corrupt entries) containing the entries import expects (`entities.xml` + `activeobjects.xml` for Jira; `entities.xml` + `exportDescriptor.properties` for Confluence). If the download is **not a ZIP** (e.g. an HTML error/login page or a truncated file), the stage **fails loudly** instead of archiving and uploading garbage that would only be rejected at restore time. A valid ZIP that's missing `entities.xml` logs a **WARNING** (surfaced now, not at restore). The Jira and Confluence stages run this check right after download (covers fresh and cooldown→existing downloads).

---

## [0.10.1] - 2026-05-27

### Added
- **`ARCHIVE_MODE` and `STORAGE_LAYOUT` are now Build-with-Parameters dropdowns** too (they were already `.env` / Configure settings + global env vars). You can switch per-product vs combined archives, and the folder depth, per run from the Jenkins form — no need to re-run Configure for a one-off. They resolve the same way as the other policy settings: an explicit non-default pick wins, otherwise the configured global env value (so CRON builds honour it), otherwise the default.

---

## [0.10.0] - 2026-05-27

### Changed
- **Per-product archives by default** — instead of one combined `atlassian-backup-<date>.7z`, each product is now archived and uploaded separately: `jira-<date>.7z` and `confluence-<date>.7z`, each with its **own manifest** (`<stem>.manifest.json`). This matches how Atlassian restore works (per product) and makes the bucket contents self-explanatory. Set `ARCHIVE_MODE=combined` (or **Configure → Archive mode**) to keep the single bundled archive.
- **Shallower storage folders** — object keys now default to **`YYYY/MM/`** (`STORAGE_LAYOUT=year-month`) instead of `YYYY/MM/DD/`; the filename already carries the full date and retention is ~30 days. Choose `year`, `year-month-day`, or `flat` via `STORAGE_LAYOUT` / **Configure → Folder layout**. Upload now ships every manifest alongside its archive.

### Added
- `ARCHIVE_MODE` and `STORAGE_LAYOUT` config (prompted in `Configure`, carried to Jenkins as global env vars by the export).

---

## [0.9.4] - 2026-05-27

### Fixed
- **Jira export download went to a broken `api.media.atlassian.com` URL** — the completion response includes a media URL whose path is malformed (it rejects with `HTTP 400 … /fileId: pattern should match`), and `download_backup` was *preferring* that URL. The download now always uses the **UI download servlet** the browser uses — `/plugins/servlet/export/download/?fileId=<uuid>` with the session cookies — which authenticates and 302-redirects to a freshly-signed media URL (followed automatically). The file UUID is extracted from the completion `result` (`<uuid>/binary`) / `fileName`, never from the media URL (which embeds the tenant `client` UUID, a different id). The existing-backup completion response is now logged for diagnosis.

---

## [0.9.3] - 2026-05-27

### Fixed
- **Upload stage was missing the required `--in` argument** — the Jenkins `Upload` step ran `backup.upload --provider … --dest …` without `--in <archive dir>`, so it died with `argparse: the following arguments are required: --in` and never uploaded. (It only surfaced now that a run first got past Jira/Confluence/Archive.) The command now passes `--in "${ARCHIVE_DIR}"`.

### Changed
- **Jira cooldown now self-heals by default** — `JIRA_COOLDOWN_ACTION` defaults to **`download-existing`** (was `skip`): when a fresh backup is blocked by the 48h cooldown, the run automatically downloads the most recent existing backup so it still produces an archive, instead of coming back empty. Set it to `skip` to keep the old behaviour.

### Added
- **Configure → Pipeline behaviour** — the interactive `Configure` flow now prompts for the **failure policy** (balanced / resilient / strict) and the **Jira cooldown action** (download-existing / skip), with inline explanations, so you set how the pipeline behaves during setup instead of hunting through build parameters.

---

## [0.9.2] - 2026-05-27

### Fixed
- **Confluence backup crashed with an opaque `Expecting value: line 1 column 1 (char 0)`** when `getprogress` returned an empty/non-JSON body. Multiple hardening fixes:
  - **Browser-like `User-Agent` + explicit `Accept: application/json`** on the Confluence requests (was a custom non-browser UA with no Accept) — some Atlassian Cloud endpoints return an HTML error/redirect page for non-browser clients, which is what failed to JSON-parse.
  - `poll_progress` tolerates a few transient non-JSON responses (retrying), then fails with the actual HTTP status + body snippet; a genuine `error`/`fail` status now fails fast instead of polling for hours.
  - The `runbackup` response is logged; 401/403 during polling exits `2` (credentials), like Jira.
- **Failure notifications failed with `module 'venv' could not be loaded`** — `cleanWs()` was in the `always{}` post block, which runs *before* `failure{}`, wiping the venv before the failure notification could use it. Moved cleanup to the `cleanup{}` block (guaranteed to run last).

### Changed
- **Warnings now print to stdout, not stderr** — so a CI runner that wraps native-command stderr as an error (Jenkins' PowerShell step) no longer makes benign warnings (e.g. the 48h-cooldown notice) look like crashes. Fatal errors still go to stderr.

---

## [0.9.1] - 2026-05-27

### Fixed
- **Jenkinsfile failed to compile** (`Expected a symbol` on every `choice` / `booleanParam`). Declarative Pipeline's `parameters{}` block only accepts **literal** values — the env-driven defaults I used (`choices: ([env.X ?: ...] + [...]).unique()` and `defaultValue: (env.STORAGE_PROVIDER ?: '').contains('gcs')`) are illegal there and broke pipeline parsing entirely. Parameters are now literals; the env-driven behaviour moved into the `Setup` stage: `resolvePolicy()` (a non-default build-parameter pick wins, else the configured global env var, else the literal default — so CRON builds still honour configured values) and storage/notify fall back to the configured global env when no checkbox is ticked.

### Changed
- **Cleaner interactive menu** — grouped into Backup / Pipeline steps / Verify & manage / Configuration with sequential numbering, instead of the cramped two-column list. (Numbers changed: Test connections is now 8, Validate 9, Export Jenkins 15, etc.)

---

## [0.9.0] - 2026-05-27

### Added
- **Per-outcome policy overrides (full control)** — on top of the `FAILURE_POLICY` presets, each outcome now has its own override parameter: `ON_COOLDOWN`, `ON_CREDENTIALS`, `ON_BACKUP_ERROR`, `ON_NO_BACKUP`, `ON_UPLOAD_FAILURE`. Each is `default` (follow the preset), `continue` (stay green), `unstable`, or `abort`, and takes precedence over the preset for that single outcome. Example: `FAILURE_POLICY=resilient` + `ON_CREDENTIALS=abort` = "keep going on everything except dead credentials." Settable per-run in *Build with Parameters* or persisted in `.env` (the export carries any non-`default` override into a Jenkins global env var).

---

## [0.8.0] - 2026-05-27

### Added
- **Configurable pipeline failure policy** — a new `FAILURE_POLICY` build parameter (and global env var) with three presets:
  - **balanced** (default): hard-fail on **expired credentials**, a **backup error/timeout**, or **no backup produced at all**; keep going (mark **UNSTABLE**) on **cooldown** and **upload-target failures**.
  - **resilient**: never abort — every problem only marks the build UNSTABLE.
  - **strict**: abort on anything that isn't a clean success.
- **`JIRA_COOLDOWN_ACTION`** parameter — on the 48h cooldown, either `skip` Jira (default; run marked UNSTABLE) or `download-existing` (download the most recent existing backup instead).
- **Exit-code contract** — the Jira/Confluence modules exit with codes the pipeline reads to classify each outcome: `0` success · `1` error/timeout · `2` credentials expired · `3` cooldown / no backup. Jenkins maps each to continue / unstable / abort per the chosen policy (`runBackup` + `policyFor` helpers).
- **Local CLI fetch-existing** — `main.py --download-existing` (and menu item *15) Fetch existing Jira backup*) downloads the most recent existing Jira backup without triggering a new one.

### Changed
- **Cooldown default is now _skip_** (was auto-download-existing in 0.7.0). Set `JIRA_COOLDOWN_ACTION=download-existing` or tick `JIRA_DOWNLOAD_EXISTING` to fetch the existing backup instead.
- **Uploads are best-effort across targets** — a failure on one storage target no longer stops the others; every reachable target still receives the archive, and the run is marked UNSTABLE (or fails, under `strict`).
- Confluence auth failures (HTTP 401/403) now exit `2` (credentials), matching Jira, so the policy treats both products' credential problems the same way.

---

## [0.7.0] - 2026-05-27

### Added
- **Independent backup stages** — a Jira failure (expired cookies, error) or cooldown no longer aborts the pipeline. The Jira and Confluence stages are wrapped so a failure marks the build **UNSTABLE** and continues; whatever backup *did* succeed is still archived and uploaded. Implemented in Jenkins (`catchError`) and mirrored in the local CLI (`do_backup` isolates each product).
- **Cooldown now ships the existing backup** — when Jira reports the 48h cooldown (HTTP 412), instead of producing nothing the run downloads the **most recent existing** Jira backup (still retained by Atlassian) so the archive/upload still happens. A new `--download-existing` flag (env `JIRA_DOWNLOAD_EXISTING=true`, or the **JIRA_DOWNLOAD_EXISTING** build parameter) forces this "fetch the latest existing backup, don't trigger a new one" mode — handy for reruns.
- **Per-product build toggles** — `BACKUP_JIRA` / `BACKUP_CONFLUENCE` checkboxes let you back up just one product. Archive and Upload are gated on a real backup `.zip` existing, so a cooldown marker alone never produces an empty upload.
- **`unstable` notification status** — notifications now render an amber ⚠️ "UNSTABLE" report (distinct from success/failure) and the Notify stage reports the build's real result.

---

## [0.6.0] - 2026-05-27

### Changed
- **Jenkins "Build with Parameters" is now checkbox-driven** (no plugin required). Storage backends and notification channels are exposed as native `booleanParam` checkboxes — one per backend (GCS / S3 / Azure / Local, each with its own destination field) and one per channel (Google Chat / Slack / Discord / Teams / Email / Webhook) — instead of hand-typed comma lists. Compression is a `0`–`9` dropdown. The `Setup` stage reassembles the aligned `STORAGE_PROVIDER` / `STORAGE_DEST` / `NOTIFY_CHANNELS` values the Python layer expects, so nothing downstream changes. If no storage box is ticked the build falls back to a local copy, so a backup is never silently skipped.

### Added
- The Jenkins export now emits **per-provider destination global env vars** (`GCS_BUCKET`, `S3_BUCKET`, `AZURE_CONTAINER`, `LOCAL_PATH`) so the new checkbox destination fields prefill from your configured `.env`.

---

## [0.5.1] - 2026-05-27

### Fixed
- **Jira export download 404** — the completion `result` field is `<uuid>/binary`, but the download servlet (`/plugins/servlet/export/download/`) expects only the bare `<uuid>` (the browser uses `?fileId=<uuid>`, no `/binary`). Passing the `/binary` suffix produced a malformed media URL and a 404. `download_backup` now strips everything from the first slash before calling the servlet, and still fetches an explicit `downloadUrl`/`mediaUrl` full URL directly when present. On failure it surfaces the HTTP status, final URL, and response body; the full completion response is logged for diagnosing instance-specific download fields.

### Changed
- **Backup poll timeout is now generous and configurable** — Jira/Confluence exports can take from minutes to several hours. The per-backup wait default is raised from 1h to **6h** (`POLL_TIMEOUT` env / `--poll-timeout`), carried to Jenkins as a build parameter and global env var. The Jenkins build wall-clock `timeout` is raised from 2h to **8h** to cover long backups plus archive and upload.

---

## [0.5.0] - 2026-05-26

### Added
- **Visible `Notify` stage** in the Jenkins pipeline (instead of only a post-action), so notification shows as its own box in the Stage View / Blue Ocean.
- **Cookie-expiry warning in notifications** — every notification warns when the Jira session cookie is within 7 days of expiry (or already expired), so operators refresh it before a backup fails.
- **Focused cookie refresh** — `main.py` → *Refresh Jira cookies* (menu) / `--refresh-cookies`: paste a fresh Copy-as-cURL, it's validated (optionally live-tested), saved to `.env`, and a tiny `update-jira-cookies.groovy` is generated that updates **only** the `jira-cookies` credential in Jenkins.
- `docs`: Blue Ocean note for visual stage tracking; monthly cookie-refresh walkthrough.

---

## [0.4.0] - 2026-05-26

### Added
- **`PYTHON_BIN`** — point the Jenkins agent at a specific Python interpreter (e.g. a full `python.exe` path) for venv creation, for when `python` isn't on the Jenkins service account's PATH. Set it in Configure / carried to Jenkins as a global env var.

### Changed
- The Jenkins venv setup **auto-detects the interpreter** — `python3`/`python` on Linux, `python`/`py` on Windows — so most agents need no `PYTHON_BIN` at all.

---

## [0.3.0] - 2026-05-26

### Added
- **Multiple storage targets** — `STORAGE_PROVIDER` and `STORAGE_DEST` accept aligned comma lists (e.g. `gcs,s3` + `bucketA,bucketB`); the archive is uploaded to every target, and the Jenkins export creates credentials for each listed provider.
- **Jenkins "Build with Parameters"** — provider(s), destination(s), S3 endpoint, notify channels, compression, and name templates are exposed as build parameters (defaulting to your configured global-env values).
- `docs/TROUBLESHOOTING.md` — common errors and fixes for end users.

### Changed
- **Schedule is configurable** — `BACKUP_CRON` (set in Configure, carried to Jenkins as a global env var) drives the `cron` trigger; no longer hardcoded.

---

## [0.2.0] - 2026-05-26

### Added
- **Cross-platform `Jenkinsfile`** — runs on Linux (`sh`) and Windows (`powershell`) agents automatically.
- **Export Jenkins setup** (`--export-jenkins` / menu option 13) — generates a Script Console Groovy script from your `.env` that creates all credentials, sets the non-secret config as Jenkins global env vars, and creates the pipeline job in one paste.
- **Storage connection test** in *Test connections* — verifies the chosen backend (gcs/s3/azure/local) is reachable and writable.
- `docs/JENKINS_SETUP.md` — full step-by-step Jenkins setup guide.
- Cookie entry accepts a full **"Copy as cURL"** paste (auto-extracted) with a retry loop and name-level validation feedback.

### Changed
- Jira requests now use browser-like headers (Windows UA, `sec-fetch-*`, no `Origin`/`Content-Type` on GET) to satisfy Atlassian's UI-only gate; *Test connections* treats HTTP 204 (no prior backup task) as success and surfaces the response body on 403.
- **Required Jira cookies relaxed** to `tenant.session.token` + `atlassian.xsrf.token`; `JSESSIONID` / `AWSALB` / `AWSALBCORS` are forwarded when present but no longer required (not all instances set them).
- Jenkins non-secret config (site, provider, destination, channels, templates, compression) is read from Jenkins global env vars, set by the export — no need to edit the shared `Jenkinsfile`.
- Muted, lower-contrast console colors; secret prompts note that input is hidden.

### Fixed
- Clear error when an unset or invalid storage provider is selected.

---

## [0.1.1] - 2026-05-26

### Changed
- Interactive **Configure** flow is now self-explanatory: it lists the choices for storage providers and notification channels, explains how to obtain the Jira cookie blob, validates the pasted cookies (reports missing ones and session-token expiry), and normalizes a bare site host to `https://`.
- Secret prompts now state that input is hidden on purpose.
- Neutral defaults — `STORAGE_PROVIDER` defaults to `local` (no account/SDK needed) and `NOTIFY_CHANNELS` defaults to none, instead of preferring GCS / Google Chat. The Configure flow no longer offers `.env.example` placeholders as defaults.
- `.env.example` is now minimal by default (local storage, no notifications) with the cloud and SMTP blocks commented out, so a fresh copy doesn't look pre-configured.

### Added
- Clear error when an unset or invalid storage provider is selected.

---

## [0.1.0] - 2026-05-26

### Added
- Initial release: full-instance backup of **Jira** and **Confluence** Cloud on the Atlassian Standard plan, restoring the automation removed by the March 2026 Backup Manager API deprecation.
- **Auth**: Jira via browser UI-session cookies + headers; Confluence via OBM Basic auth (email + API token). One Atlassian admin account drives both.
- **Pluggable storage**: upload to Google Cloud Storage, AWS S3 / S3-compatible (Cloudflare R2, Backblaze B2, MinIO, DigitalOcean Spaces), Azure Blob, or a local directory. Each cloud SDK is an optional extra.
- **Pluggable notifications**: Google Chat, Slack, Discord, Microsoft Teams, email (SMTP), and a generic webhook — any combination, no extra dependencies.
- **Archiving**: 7-Zip with optional AES-256 encryption (encrypted headers) and a configurable compression level (0–9).
- **Configurable filenames** via templates (`{product} {site} {date} {time} {datetime} {timestamp}`).
- **Integrity**: a `manifest.json` (sha256 + `complete` flag) is written and uploaded with each backup; `--validate` verifies the archive, `--cleanup` prunes incomplete/old backups, `--skip-existing` avoids re-running, `--dry-run` previews any flow.
- **Dual-mode entrypoint**: interactive menu for VMs and CLI flags for automation; installable as the `jira-confluence-backup` console script and runnable via `python -m backup`.
- **Jenkins pipeline** (`Jenkinsfile`) with independent stages, 48-hour cooldown handling (HTTP 412 keeps the build green), and credentials bound from the Jenkins Credentials store.
- **Connection test** with Jira session-token (JWT) expiry warning.
- `rich`-optional, ASCII-safe console output (safe on legacy Windows consoles).

[0.13.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.13.0
[0.12.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.12.1
[0.12.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.12.0
[0.11.2]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.11.2
[0.11.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.11.1
[0.11.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.11.0
[0.10.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.10.1
[0.10.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.10.0
[0.9.4]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.9.4
[0.9.3]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.9.3
[0.9.2]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.9.2
[0.9.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.9.1
[0.9.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.9.0
[0.8.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.8.0
[0.7.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.7.0
[0.6.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.6.0
[0.5.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.5.1
[0.5.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.5.0
[0.4.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.4.0
[0.3.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.3.0
[0.2.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.2.0
[0.1.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.1
[0.1.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.0
