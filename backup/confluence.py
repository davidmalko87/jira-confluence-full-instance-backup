"""
Confluence full-site backup via OBM REST API.

Auth model: Basic auth with email + API token. This is the same flow the
PowerShell script has been running reliably; just ported to Python so it
lives in the same pipeline as the Jira stage.

The OBM API never got the UI-only lockdown that hit Jira's backup endpoint.

OBM response shape (getprogress):
{
  "fileName": "...",
  "size": <bytes>,
  "concurrentBackupInProgress": false,
  "alternativePercentage": "x%",
  "time": <ms>,
  "isOutdated": false,
  "currentStatus": "..."   # use this field, NOT "size", for completion check
}

A 406 on runbackup is cosmetic — the backup actually starts. Treat as success.
14-day Filestore retention applies once the file appears.
"""
import argparse
import base64
import os
import sys
import time
from pathlib import Path

import requests

from . import naming, ui


USER_AGENT = "atlassian-weekly-backup/1.0"


def basic_auth_header(email: str, token: str) -> str:
    raw = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def trigger_backup(site: str, auth_header: str) -> dict:
    """
    POST /wiki/rest/obm/1.0/runbackup
    A 406 here is cosmetic — backup starts anyway.
    """
    url = f"{site}/rest/obm/1.0/runbackup"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Atlassian-Token": "no-check",
    }
    body = {"cbAttachments": True, "exportToCloud": True}

    resp = requests.post(url, headers=headers, json=body, timeout=60)

    if resp.status_code == 406:
        print("[INFO] runbackup returned 406 (cosmetic, backup started anyway)")
        return {}

    if resp.status_code >= 400:
        print(f"[ERROR] runbackup {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()

    try:
        return resp.json()
    except ValueError:
        return {}


def poll_progress(site: str, auth_header: str,
                  timeout_sec: int = 21600, interval_sec: int = 30) -> dict:
    """
    GET /wiki/rest/obm/1.0/getprogress
    Completion when currentStatus contains 'completed' / file ready.
    """
    url = f"{site}/rest/obm/1.0/getprogress"
    headers = {
        "Authorization": auth_header,
        "User-Agent": USER_AGENT,
    }

    deadline = time.time() + timeout_sec
    poll_count = 0

    while time.time() < deadline:
        poll_count += 1
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        current_status = (data.get("currentStatus") or "").lower()
        file_name = data.get("fileName", "")
        size = data.get("size", 0)
        pct = data.get("alternativePercentage", "0%")

        ui.info(f"[poll {poll_count}] status='{current_status}' "
                f"file='{file_name}' size={size} pct={pct}")

        # OBM completion signals: status text + fileName populated
        if file_name and ("complete" in current_status or "success" in current_status):
            return data

        # Fallback: fileName present + size > 0 + no error
        if file_name and size > 0 and "error" not in current_status:
            return data

        time.sleep(interval_sec)

    raise TimeoutError(f"Confluence backup did not complete within {timeout_sec}s")


def download_backup(site: str, auth_header: str, file_name: str,
                    out_path: Path, show_progress: bool = False) -> int:
    """
    GET /wiki/download/temp/filestore/{file_name}
    Streams to disk. Returns bytes written.
    """
    # site already includes /wiki — strip and reconstruct the download path
    base = site.rstrip("/")
    if base.endswith("/wiki"):
        base = base[: -len("/wiki")]

    url = f"{base}/wiki/download/temp/filestore/{file_name}"
    headers = {
        "Authorization": auth_header,
        "User-Agent": USER_AGENT,
    }

    bytes_written = 0
    with requests.get(url, headers=headers, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0) or None

        def _stream(update=None):
            nonlocal bytes_written
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)
                        if update:
                            update(len(chunk))

        if show_progress:
            with ui.progress_bar(total, f"Downloading {out_path.name}") as update:
                _stream(update)
        else:
            _stream()

    return bytes_written


def test_connection(site: str, email: str, token: str) -> tuple[bool, str]:
    """Non-exiting check: API token can authenticate against the site."""
    if not email or not token:
        return False, "ATL_EMAIL / ATL_TOKEN not set"
    base = site.rstrip("/")
    url = f"{base}/rest/api/user/current" if base.endswith("/wiki") \
        else f"{base}/wiki/rest/api/user/current"
    try:
        resp = requests.get(url, headers={"Authorization": basic_auth_header(email, token),
                                          "User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as exc:
        return False, f"Request failed: {exc}"
    if resp.status_code == 200:
        try:
            who = resp.json().get("publicName") or resp.json().get("displayName") or email
        except ValueError:
            who = email
        return True, f"Confluence token valid (as {who})"
    if resp.status_code in (401, 403):
        return False, f"Auth rejected (HTTP {resp.status_code}) — check email/token"
    return False, f"Unexpected HTTP {resp.status_code}"


def run_backup(site: str, email: str, token: str, out_dir: Path,
               name_template: str = naming.DEFAULT_PRODUCT_TEMPLATE,
               poll_timeout: int = 21600) -> Path:
    """Full trigger→poll→download flow. Returns the downloaded .zip path."""
    auth_header = basic_auth_header(email, token)
    out_dir.mkdir(parents=True, exist_ok=True)

    ui.info(f"Triggering Confluence backup on {site}")
    trigger_backup(site, auth_header)

    ui.info("Polling progress")
    final = poll_progress(site, auth_header, timeout_sec=poll_timeout)

    file_name = final.get("fileName")
    if not file_name:
        raise RuntimeError(f"No fileName in completion response: {final}")

    out_path = out_dir / naming.render_name(name_template, "confluence",
                                            ext=".zip", site=site)
    size = download_backup(site, auth_header, file_name, out_path, show_progress=True)
    ui.ok(f"Confluence backup: {out_path} ({size / (1024 * 1024):.1f} MB)")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True,
                        help="Confluence root, e.g. https://<YOUR_SITE>.atlassian.net/wiki")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--poll-timeout", type=int,
                        default=int(os.environ.get("POLL_TIMEOUT", "21600")),
                        help="Max seconds to wait for backup to complete "
                             "(default 21600 = 6h; env: POLL_TIMEOUT)")
    parser.add_argument("--name-template",
                        default=os.environ.get("PRODUCT_NAME_TEMPLATE",
                                               naming.DEFAULT_PRODUCT_TEMPLATE),
                        help="Filename template (tokens: {product}{site}{date}"
                             "{time}{datetime}{timestamp})")
    args = parser.parse_args()

    email = os.environ.get("ATL_EMAIL")
    token = os.environ.get("ATL_TOKEN")
    if not email or not token:
        sys.exit("ATL_EMAIL / ATL_TOKEN env vars not set")

    try:
        run_backup(args.site, email, token, args.out,
                   name_template=args.name_template, poll_timeout=args.poll_timeout)
    except (RuntimeError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
