# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.4.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.4.0
[0.3.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.3.0
[0.2.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.2.0
[0.1.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.1
[0.1.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.0
