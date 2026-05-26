# Contributing

Thanks for helping improve this project!

## Before you start — read `CLAUDE.md`

It captures empirically-validated findings that are easy to get wrong:

- **Jira backup is gated to UI sessions.** It needs browser session cookies +
  UI headers. **Do not** propose replacing this with an API token — Atlassian
  returns `403 {"error":"This feature is only accessible from the UI."}`.
- Confluence uses OBM Basic auth (email + API token).
- Response-code semantics (200 / 403 / 412 / 400 / 406) and the exact request
  body format are documented and were derived empirically.

## Ground rules

- **No secrets, ever.** Never commit real cookies, tokens, emails, site URLs, or
  bucket names. Use placeholders and `.env.example`. `.env` is gitignored.
- **Keep core dependencies minimal** (stdlib + `requests`). New cloud providers
  go in their own `requirements-<provider>.txt` and import lazily.
- **ASCII-only console output.** `rich` is optional and used for color only;
  never emit non-ASCII glyphs (they crash the legacy Windows console).
- **Test auth/backup changes against a non-prod Atlassian instance first.**
  Atlassian's error responses are inconsistent (400 sometimes surfaces as 403).

## Dev workflow

```bash
pip install -r requirements.txt
pip install ruff
ruff check .
python -m backup --help
python main.py --help
```

Branch naming: `feature/...` or `fix/...`. Commits: imperative mood, concise.
Update `CHANGELOG.md` for user-facing changes.

## Exit-code convention

- `0` — success (or graceful skip like cooldown)
- `1` — generic failure
- `2` — human action needed (refresh cookies, fix credentials)

## Releases

Maintainers bump `__version__` in `backup/__init__.py`, update `CHANGELOG.md`,
then tag `vX.Y.Z`. The `publish.yml` workflow builds and publishes to PyPI via
Trusted Publishing.
