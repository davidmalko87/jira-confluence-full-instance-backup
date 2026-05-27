# Restoring a backup

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

## 2. Jira

The Jira export (`entities.xml` + `activeobjects.xml` inside) is restored via
Atlassian's Jira site import. It is intended for **cloud-to-cloud migration or a
fresh/empty site** — importing a full backup *over* an existing populated Jira
Cloud site is restricted. See Atlassian's
[Import and export](https://support.atlassian.com/jira-cloud-administration/docs/import-and-export-data/)
docs for the current procedure and constraints.

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

> You do **not** hand-edit or cherry-pick files out of `Site_Backup.zip` — where
> full import is available, you upload the whole `.zip`.

## 4. Why keep our own copy?

Atlassian deletes the backup from its Filestore after **14 days**, and the Jira
backup is throttled to one every 48h. Storing the `.7z` in your own bucket (with
a lifecycle rule for retention — see [JENKINS_SETUP](JENKINS_SETUP.md#retention--rotation-delete-old-backups))
means you always have a recent, verified copy regardless of Atlassian's
short-lived links.
