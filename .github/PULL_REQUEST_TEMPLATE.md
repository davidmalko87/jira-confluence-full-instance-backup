<!-- Before changing auth code, read CLAUDE.md — the Jira UI-session gate is real;
     do not replace cookie auth with API tokens. -->

## Summary

<!-- What does this PR change and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature (storage provider / notify channel / CLI)
- [ ] Docs / CI
- [ ] Refactor

## Checklist

- [ ] `ruff check .` passes
- [ ] `python -m backup --help` and `python main.py --help` work
- [ ] No secrets, cookies, tokens, or real site identifiers committed
- [ ] New cloud SDKs kept optional (`requirements-<provider>.txt`), not core
- [ ] Tested against a non-prod Atlassian instance (if touching backup/auth)
- [ ] CHANGELOG.md updated for user-facing changes
