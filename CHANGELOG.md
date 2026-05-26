# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-26

Initial release.

### Added
- Full-instance backup of **Jira** (UI-session cookies + headers) and
  **Confluence** (OBM Basic auth) Cloud on the Standard plan.
- **Jenkins pipeline** (`Jenkinsfile`) with independent stages and 48h-cooldown
  handling (HTTP 412 keeps the build green).
- **Dual-mode `main.py`**: interactive menu for VMs + CLI flags for automation;
  also installable as the `jira-confluence-backup` console script and runnable
  via `python -m backup`.
- **Pluggable storage**: GCS, S3 / S3-compatible (R2, B2, MinIO, Spaces), Azure
  Blob, and local — each SDK optional (`requirements-<provider>.txt`).
- **Pluggable notifications**: Google Chat, Slack, Discord, Teams, email (SMTP),
  and a generic webhook — no extra dependencies.
- **7-Zip archiving** with optional AES-256 encryption and configurable
  compression level (0–9).
- **Configurable filenames** via templates (`{product} {site} {date} {time}
  {datetime} {timestamp}`).
- **manifest.json** with sha256 integrity + `--validate`, plus `--cleanup`,
  `--dry-run`, and `--skip-existing`.
- **Connection test** with Jira session-token (JWT) expiry warning.
- `rich`-optional, ASCII-safe console output (safe on legacy Windows consoles).

[0.1.0]: https://github.com/davidmalko87/jira-confluence-full-instance-backup/releases/tag/v0.1.0
