# jira-confluence-full-instance-backup

Jenkins pipeline that performs **full-instance backup** of Jira Cloud and
Confluence Cloud to Google Cloud Storage. Designed for Atlassian **Standard
plan** customers who lost their automated backup option after the March 2026
Backup Manager API deprecation.

For per-project (granular) Jira backup/restore, see the sibling repo
`jira-project-backup-restore`.

---

## Critical context — read this before changing auth code

The two products require **different auth mechanisms**. This is non-obvious and
caused weeks of confusion before we pinned it down empirically:

| Product    | Endpoint                                | Auth                        | Why                                          |
|------------|-----------------------------------------|-----------------------------|----------------------------------------------|
| Confluence | `/wiki/rest/obm/1.0/runbackup`          | Basic (email + API token)   | OBM never got the UI-only lockdown           |
| Jira       | `/rest/backup/1/export/runbackup`       | Session cookies + UI headers | Atlassian gates this endpoint to UI sessions |

**Do not try to "simplify" the Jira side to use API tokens.** It returns:

```
HTTP 403
{"error":"This feature is only accessible from the UI."}
```

This is confirmed behavior post-March 2026. We tested it on two separate
non-prod instances with multiple body formats. There is no API-token path on
the Standard plan. The Premium/Enterprise v2 API
(`api.atlassian.com/public/backup-management/v2/`) is paywalled and out of
scope for this project.

---

## Jira request contract (empirically validated)

**Body format that the modern UI sends (✅ works with cookies):**

```json
{"cbAttachments": "true", "exportToCloud": "true"}
```

Strings, not booleans. No `"what"` field.

**Body formats that fail:**

- `{"cbAttachments": true, "exportToCloud": true, "what": "all"}` → 400 `"Invalid request payload"` (`"what"` field rejected by current schema)
- Any body via Basic auth (API token) → 403 `"This feature is only accessible from the UI."`

**Required headers** (without these, requests fail even with valid cookies):

- `X-Requested-With: XMLHttpRequest`
- `Referer: <site>/secure/admin/CloudExport.jspa`
- `Origin: <site>`
- `Content-Type: application/json`
- Realistic `User-Agent`

**Required cookies** (everything else in the captured blob is tracking noise):

- `tenant.session.token` — JWT, ~30 day lifetime, the critical one
- `atlassian.xsrf.token` — XSRF protection
- `JSESSIONID` — servlet session
- `AWSALB`, `AWSALBCORS` — load balancer sticky routing

---

## Response code semantics

| Code | Meaning                         | Pipeline behavior                                    |
|------|---------------------------------|------------------------------------------------------|
| 200  | Backup queued / status returned | Continue to polling                                  |
| 403  | Auth rejected (UI-only gate)    | Exit code 2 — cookies expired, needs manual refresh  |
| 412  | 48-hour cooldown active         | Exit code 0 + marker file — build stays green        |
| 400  | Body schema rejected            | Bug in this script — investigate body format         |
| 406  | Confluence cosmetic error       | Ignore, backup actually started                      |

The 412 vs 403 distinction matters: cooldown is operational reality and must
not fail the build. Auth gate is real failure and must fail clearly.

---

## Architecture

```
Jenkins job (cron Thursday 02:00)
  └─ Setup → Jira → Confluence → Archive → GCS upload → Notify
```

Stages are independent. Cookie expiry kills Jira but not Confluence.

Auth credentials live in Jenkins Credentials store, never in repo or env files:

- `jira-cookies` (Secret text) — full cookie blob, manually refreshed monthly
- `atlassian-email`, `atlassian-api-token` (Secret text) — Confluence Basic auth
- `archive-password` (Secret text) — 7-Zip AES-256 passphrase
- `gcp-backup-sa-key` (Secret file) — GCS service account JSON
- `chat-webhook` (Secret text) — Google Chat webhook URL

---

## Conventions

- **Python 3.10+** — uses `|` union syntax in type hints
- **Standard library + `requests` + `google-cloud-storage`** only — no heavy frameworks
- **No secrets in code**, ever — all sensitive values via env vars bound from Jenkins Credentials
- **No site identifiers hardcoded** — `--site` arg or env var, never a literal URL in source
- **stdout for progress, stderr for errors** — Jenkins log readability
- **Exit code 2 for "needs human action"** (cookie refresh) — distinct from generic failure (exit 1)
- **Never print credentials, cookies, or tokens** — even on debug

---

## Code style

- `argparse` for CLI args (not click/typer — keep deps minimal)
- Module-level `main()` function, `if __name__ == "__main__"` guard
- f-strings, no `.format()` or `%`
- 4-space indent, 100-char line limit
- Type hints encouraged but not enforced

---

## Operational facts

- **Cooldown:** 48 hours between Jira backups. Weekly cadence is well within budget.
- **Filestore retention:** Confluence backup file is auto-deleted after 14 days.
- **Cookie lifetime:** `tenant.session.token` JWT lives ~30 days. Build fails clearly when expired.
- **GCS lifecycle:** bucket has 28-day delete rule. This script does not manage rotation.
- **GCS scope:** service account has `roles/storage.objectCreator` at bucket level. It can write but not read or delete.

---

## Things to do when changing code

- **Adding fields to request bodies:** test on a non-prod Atlassian instance first. Atlassian's error responses are inconsistent (400 sometimes surfaces as 403); empirical testing beats reading docs.
- **Changing dependencies:** keep `requirements.txt` minimal. New deps need justification in PR.
- **Changing auth flow:** re-read the "Critical context" section above. Do not assume "modern" auth approaches work — Atlassian gates this endpoint specifically.
- **Adding a new product (e.g. Bitbucket):** new module under `backup/`, new Jenkins stage. Don't entangle with existing modules.

---

## Out of scope

- Restore automation. This project handles backup only. Restore on Standard plan is manual via Atlassian's import UI, or via `jira-project-backup-restore` for per-project granular restore.
- Premium/Enterprise v2 backup API (`api.atlassian.com/public/backup-management/v2/`).
- Per-project Jira backups — see separate `jira-project-backup-restore` repo.
