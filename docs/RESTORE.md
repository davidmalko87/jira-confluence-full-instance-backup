# Restoring a backup

![Jira restore: round-trip verified](https://img.shields.io/badge/Jira%20restore-round--trip%20verified%20(2026--06--03)-brightgreen.svg)

This project produces **full-instance** backups (the same files Atlassian's own
Backup Manager / export produces) and stores them safely off-platform. Restore
itself is **manual**, through Atlassian's import UI — this tool does not restore.

> **What these backups are for:** disaster recovery and migration — rebuilding a
> site, or moving to a fresh Cloud site / to Confluence Server/DC. Restoring
> *into a live Cloud site that already has data* has Atlassian-imposed limits
> (below) that no backup tool can remove. For day-to-day granular restore of a
> single Jira project, see the sibling `jira-project-backup-restore`.

## 1. Get the raw Atlassian file out of the archive

Each product is stored as `<product>-<date>.7z`, which simply *wraps* the
original Atlassian `.zip` (byte-for-byte; the `manifest.json` records its
sha256). Download the `.7z` from your storage and extract it:

```bash
7z x jira-2026-05-27.7z          # -> jira-2026-05-27.zip   (Jira export)
7z x confluence-2026-05-27.7z    # -> confluence-2026-05-27.zip (Confluence Site_Backup)
```

If you set `ARCHIVE_PASSWORD`, add `-p<password>`. The extracted `.zip` is what
you feed to Atlassian's importer.

## 2. Jira — ✅ verified end-to-end

Restore via **Jira admin → System → Import and export → Import Jira cloud**
(`/secure/admin/CloudImport!start.jspa?source=CLOUD`): pick **Import data**,
upload the extracted `.zip` as the *data file*, Atlassian validates it, then you
run the import. (Note: the legacy Server path `/secure/admin/Restore!default.jspa`
is a **dead link** on Cloud — use *Import Jira cloud*.)

> **Verified live — 2026-06-03, Standard combined site.** A backup produced by
> this tool was uploaded to *Import Jira cloud* as the data file (the per-product
> `jira-<date>.zip` = `entities.xml` + `activeobjects.xml`). Atlassian's importer
> validated it — *"We've checked your file for issues, and everything looks
> good"* — reading the correct **source site** and **backup timestamp** from the
> file, then ran the overwrite import to completion (`CloudImport!progress`).
> Restore fidelity was then confirmed **issue-by-issue** via the REST API: every
> item that existed at backup time came back (direct `GET /rest/api/3/issue/<key>`
> → 200, e.g. `KAN-1`, `SAM1-1`), and every item created *after* the backup
> timestamp was correctly **absent** (→ 404) — i.e. the site was restored to
> exactly the backed-up point-in-time snapshot, no more and no less.

Key points:
- The import **overwrites** existing Jira data (projects, issues, attachments,
  configuration) and reverts the site to the backup's **point in time** — anything
  created *after* the backup is gone (verified above). Users/groups are **merged**
  (you choose the merge behavior), which can change their group membership/
  permissions — review before importing.
- **Disable outgoing mail** on the import confirmation screen for a test/DR
  restore, so the import doesn't blast notification emails to users.
- The final **Run import** is a **destructive, UI-gated** step — there is no
  API-token import path (the mirror of why the *backup* side needs cookies).
- **Large instances:** Atlassian recommends splitting the export into a *data*
  file (`activeobjects.xml` + `entities.xml`) and a *media* file (attachments),
  with the `.xml` ≤ 20 GB (split media > 10 GB into 2–5 GB chunks). This is a
  restore-time step — the backup already contains everything. See the
  [split-a-Jira-export KB](https://confluence.atlassian.com/cloudkb/how-to-import-only-part-of-a-jira-export-into-jira-cloud-859461966.html).
- **Free-plan** sites cap imported active users (10; 3 JSM agents); importing
  more upgrades the plan.

Full procedure: [Importing issues / Import and export](https://support.atlassian.com/jira-cloud-administration/docs/import-and-export-data/).

## 3. Confluence

Our file is the official **`Site_Backup.zip`** from Confluence's *Backup manager*
(Settings → Backup manager). Atlassian's own pages spell out the restore paths:

- **To Confluence Server / Data Center 6.0+** — full site import works.
- **To a Confluence Cloud site** — *"You may be able to restore this backup into
  this or another Confluence Cloud site, with some limitations."*
- **⚠️ If the Cloud site has BOTH Confluence and Jira (most sites do):**
  full **site import is _not_ available**. Atlassian requires you to
  **import spaces one at a time** instead — see
  [Import a Confluence Cloud space](https://support.atlassian.com/confluence-cloud/docs/import-a-confluence-cloud-space/).

  Per-space import expects a **per-space export** file, which is a *different*
  artifact from the full `Site_Backup.zip`. So the full backup is your
  **whole-site DR / Server-migration** copy; for granular per-space restore into
  a live combined Cloud site you would use per-space exports.

> **Confirmed live — 2026-06-03 (combined site).** The **Import Confluence spaces**
> screen (Settings → … → *space import*) states plainly: *"Only space exports can
> be imported."* It accepts a **single-space export**, not the full-site
> `Site_Backup.zip` this tool produces — so on a combined Jira+Confluence Cloud
> site the full Confluence backup is **not directly importable** through this UI.
> The page also warns the import **triggers a site reindex**, **can't import
> whiteboards** (content/layout lost), and may shift role-based access into
> *"transition"* mode. For granular restore, use Confluence's own per-space export
> as the import file.

> You do **not** hand-edit or cherry-pick files out of `Site_Backup.zip` — where
> full import is available, you upload the whole `.zip`.

## 4. Why keep our own copy?

Atlassian deletes the backup from its Filestore after **14 days**, and the Jira
backup is throttled to one every 48h. Storing the `.7z` in your own bucket (with
a lifecycle rule for retention — see [JENKINS_SETUP](JENKINS_SETUP.md#retention--rotation-delete-old-backups))
means you always have a recent, verified copy regardless of Atlassian's
short-lived links.
