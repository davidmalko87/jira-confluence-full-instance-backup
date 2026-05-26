"""Full-instance backup of Atlassian Cloud (Jira + Confluence) to Google Cloud Storage.

Modules are invoked as ``python -m backup.<name>`` from the Jenkins pipeline:
jira, confluence, archive, gcs_upload, notify.
"""
