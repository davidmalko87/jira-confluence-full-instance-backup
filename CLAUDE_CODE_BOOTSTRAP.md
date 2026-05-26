# Claude Code bootstrap prompt

Paste this into your first Claude Code session in the repo directory. It sets
context, names priorities, and prevents Claude Code from rewriting things
that don't need rewriting.

---

```
We are preparing this repo for open-source release. It is a Jenkins-driven
pipeline that performs full-instance backup of Atlassian Cloud (Jira +
Confluence) on the Standard plan, where Atlassian's March 2026 API
deprecation removed the official automation path.

Start by reading these files in order:
1. CLAUDE.md — hard constraints, auth findings, response code semantics
2. README.md — current setup docs
3. Jenkinsfile — pipeline shape
4. backup/jira.py and backup/confluence.py — the two auth paths

Then do the following, in this order:

1. Genericize: Find every hardcoded reference to your real Atlassian site
   domain or your storage bucket/container name in README.md, Jenkinsfile, and
   any comments. Replace with placeholders (<YOUR_SITE>.atlassian.net,
   <YOUR_BUCKET>) and add a "Configuration" section to README.md explaining
   how to set the actual values.

2. Add a config.example file (or .env.example) showing every env var the
   pipeline expects, with placeholder values and inline comments explaining
   each one. No real secrets.

3. Verify the Jira task-ID extraction logic in backup/jira.py is robust. The
   field name in the runbackup response is uncertain — we coded fallbacks
   (taskId, id, result), and a lastTaskId fetch fallback. Confirm those are
   in the right order and that the error path (no task ID found) prints the
   raw response for debugging.

4. Add unit tests for the cookie blob parser in backup/jira.py
   (parse_cookie_blob). It is the most likely place for breakage when users
   paste cookies from their browser. Cover: missing cookies (should exit 2),
   extra whitespace, semicolons inside values (none expected but defensive),
   empty input.

5. Add a basic CONTRIBUTING.md explaining: how to test changes against a
   real Atlassian instance, the "never simplify the Jira auth to API tokens"
   rule (with a link to the CLAUDE.md section explaining why), and the
   exit-code convention (0 = success, 1 = generic failure, 2 = human action
   needed).

6. Run a final pass to check that no secrets, real cookies, real tokens, or
   real email addresses leak into any committed file.

Constraints:
- Do not rewrite working code for stylistic reasons. The modules are
  intentionally minimal.
- Do not add new dependencies without asking first.
- Do not change the auth architecture — see CLAUDE.md "Critical context".
- All code changes go through a feature branch and PR, never direct to main.

Confirm you've read CLAUDE.md and the four files above, then propose your
plan as a numbered checklist before making any changes.
```

---

## After the first session

Once the open-source baseline is in place, future sessions can be short and
task-focused:

- `Read CLAUDE.md. Add support for backing up Bitbucket Cloud as a third
  stage. Same pattern as the existing modules.`
- `Read CLAUDE.md. The Jira task-ID field name changed in the response. Here
  is the raw response we got: [paste]. Patch backup/jira.py.`
- `Read CLAUDE.md. Add a --dry-run flag to backup/jira.py that triggers
  runbackup but skips the polling and download stages.`

CLAUDE.md is the project's persistent brain. Update it whenever you discover
a new hard constraint that Claude Code would need to know in 6 months.

## Memory management commands inside Claude Code

- `/memory` — see what Claude Code has learned automatically about the project
- `#` prefix at the start of a message — add a one-time rule to the session
  (e.g. `# Always use 4-space indents, never tabs`)
- Add permanent rules by editing CLAUDE.md directly
- `CLAUDE.local.md` — personal/private rules, gitignored (already in .gitignore)
