# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.1
[0.1.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.0
