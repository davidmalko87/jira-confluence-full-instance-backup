# Contributing

## Versioning

This project uses [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

| Change type | Bump | Example |
|---|---|---|
| Backward-incompatible change | MAJOR | `0.x.x` → `1.0.0` |
| New backward-compatible feature | MINOR | `0.1.x` → `0.2.0` |
| Bug fix or small improvement | PATCH | `0.1.0` → `0.1.1` |

### How to bump the version

1. **Edit `backup/__init__.py`** — the single source of truth:
   ```python
   __version__ = "0.1.1"   # update this line
   ```
   `pyproject.toml` reads the version dynamically from this attribute, so it is
   the only place to change it.

2. **Add an entry to `CHANGELOG.md`** at the top of the file:
   ```markdown
   ## [0.1.1] - YYYY-MM-DD

   ### Fixed
   - Short description of the change.
   ```

Both files must be updated together in the same commit as the change that
warrants the bump.

---

## Publishing a Release

Follow these steps in order every time a new version is ready:

### 1. Bump the version and update docs
- `backup/__init__.py` — update `__version__`
- `CHANGELOG.md` — add a new entry at the top

### 2. Commit and push
```bash
git add backup/__init__.py CHANGELOG.md
git commit -m "Bump version to X.Y.Z"
git push
```

### 3. Create a GitHub Release
- Go to **Releases → Draft a new release**
- Tag: `vX.Y.Z`
- Title: `vX.Y.Z`
- Body: paste the new section from `CHANGELOG.md`
- Click **Publish release**

### 4. PyPI publishes automatically
Pushing the `vX.Y.Z` tag triggers the **Publish to PyPI** workflow
(`.github/workflows/publish.yml`), which builds the sdist + wheel and uploads
them to PyPI via **Trusted Publishing** (OIDC — no API token in the repo).
Watch the run under the **Actions** tab; the first run may ask a maintainer to
approve the `pypi` environment.

---

## Development

```bash
pip install -r requirements.txt        # core (requests)
pip install -r requirements-ui.txt     # optional: rich (nicer menu output)
pip install ruff
ruff check .
python -m backup --help
python main.py --help
```

### Ground rules

- **No secrets, ever.** Never commit real cookies, API tokens, emails, site
  URLs, or bucket/container names. Use placeholders and `.env.example`; `.env`
  is gitignored.
- **Keep core dependencies minimal** (stdlib + `requests`). New cloud providers
  go in their own `requirements-<provider>.txt` and import lazily.
- **ASCII-only console output.** `rich` is optional and used for color only;
  never emit non-ASCII glyphs (they crash the legacy Windows console).
- **Jira auth uses a browser UI session** (cookies + headers). Do **not** switch
  it to API-token Basic auth — Atlassian gates that endpoint and returns
  `403 "This feature is only accessible from the UI."` See the README
  "Auth model" section.
- **Test backup/auth changes against a non-prod Atlassian instance first.**
  Atlassian's error responses are inconsistent (400 sometimes surfaces as 403).

### Exit-code convention

- `0` — success (or graceful skip like cooldown)
- `1` — generic failure
- `2` — human action needed (refresh cookies, fix credentials)

---

## Adding a provider or channel

- **Storage backend:** add a function to the `BACKENDS` registry in
  `backup/upload.py` and a `requirements-<provider>.txt`. Keep the SDK import
  lazy so it stays optional.
- **Notification channel:** add a renderer to the `CHANNELS` registry in
  `backup/notify.py`. Webhook-based channels need no new dependency; email uses
  the stdlib.
