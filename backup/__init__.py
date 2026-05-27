"""Full-instance backup of Atlassian Cloud (Jira + Confluence).

Backs up to pluggable cloud storage (GCS / S3 / Azure / local). Modules run as
``python -m backup.<name>`` from the Jenkins pipeline (jira, confluence,
archive, upload, notify); the dual-mode CLI/menu is ``backup.cli`` (also the
``jira-confluence-backup`` console script and ``python -m backup``).
"""
__version__ = "0.9.0"
