"""
Jira full-instance backup via cookie-authenticated UI session.

Auth model: replays browser session cookies + UI headers (X-Requested-With, Referer, Origin).
API token + Basic auth does NOT work — Atlassian gates this endpoint to UI sessions only.

Cookies expire roughly every 30 days (tenant.session.token JWT). When that happens,
this script returns exit code 2 — Jenkins flags the build, you refresh cookies in
Jenkins Credentials, next run succeeds.

48-hour cooldown is handled gracefully (exit 0 with marker file, not a failure).
"""
import argparse
import base64
import binascii
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import naming, ui


# Cookies the backup endpoint actually needs. Only the auth + XSRF cookies are
# universally required. JSESSIONID / AWSALB / AWSALBCORS are servlet / load-balancer
# cookies that SOME instances set and others don't — they are forwarded if present
# but not required (an instance that truly needs them will 403 at request time,
# which is handled). Everything else in the blob (ajs_*, intercom-*, theme prefs,
# consent tokens) is noise but harmless — all cookies are sent through as-is.
REQUIRED_COOKIES = [
    "tenant.session.token",   # JWT auth — the critical one, ~30 day lifetime
    "atlassian.xsrf.token",   # XSRF protection
]
# Forwarded automatically when present; not all instances use them.
OPTIONAL_COOKIES = ["JSESSIONID", "AWSALB", "AWSALBCORS"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def cookies_from_blob(blob: str) -> dict:
    """Parse 'name=value; name2=value2; ...' into a dict (no validation)."""
    cookies = {}
    for part in blob.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies[name.strip()] = value.strip()
    return cookies


def missing_cookies(cookies: dict) -> list[str]:
    return [c for c in REQUIRED_COOKIES if c not in cookies]


# Pull the cookie string out of a pasted "Copy as cURL" command or a raw
# "Cookie:" request header, so the user can paste the whole thing.
_CURL_COOKIE_RE = re.compile(r"(?:-b|--cookie)\s+(['\"])(?P<v>.*?)\1", re.DOTALL)
_HEADER_COOKIE_RE = re.compile(r"[Cc]ookie:\s*(?P<v>[^'\"\r\n]+)")


def extract_cookie_blob(text: str) -> str:
    """Accept a full cURL command, a 'Cookie:' header, or an already-clean
    blob, and return the bare 'name=value; ...' cookie string."""
    t = (text or "").strip()
    m = _CURL_COOKIE_RE.search(t)
    if m:
        return m.group("v").strip()
    m = _HEADER_COOKIE_RE.search(t)
    if m:
        return m.group("v").strip().rstrip(";").strip()
    return t


def parse_cookie_blob(blob: str) -> dict:
    """Parse and validate the cookie blob; exit 2 if required cookies are absent."""
    cookies = cookies_from_blob(blob)
    missing = missing_cookies(cookies)
    if missing:
        print(f"[ERROR] Required cookies missing from JIRA_COOKIES: {missing}",
              file=sys.stderr)
        print("[HINT] Refresh cookies — see README cookie-refresh procedure",
              file=sys.stderr)
        sys.exit(2)
    return cookies


def session_token_days_left(cookies: dict) -> float | None:
    """Decode the tenant.session.token JWT 'exp' (no signature check) → days left."""
    token = cookies.get("tenant.session.token", "")
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError):
        return None
    exp = data.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return (exp - time.time()) / 86400


def ui_headers(site: str, *, for_get: bool = False) -> dict:
    """
    Headers that make the request look browser-originated to Atlassian's UI-only
    gate. POST (runbackup) sends Origin + Content-Type; GET requests (a browser
    XHR) send neither — sending them on a GET can trip the gate.
    """
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": site,
        "Referer": f"{site}/secure/admin/CloudExport.jspa",
        "X-Requested-With": "XMLHttpRequest",
        "X-Atlassian-Token": "no-check",
        "User-Agent": USER_AGENT,
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    if for_get:
        headers.pop("Content-Type", None)
        headers.pop("Origin", None)
    return headers


def trigger_backup(site: str, cookies: dict) -> dict | None:
    """
    POST /rest/backup/1/export/runbackup
    Returns parsed response dict, or None if cooldown active (412).
    Raises on other errors.
    """
    url = f"{site}/rest/backup/1/export/runbackup"
    # Body shape that matches the browser UI exactly (strings, no "what" field).
    # Confirmed empirically via captured cURL — booleans + "what":"all" returns
    # "Invalid request payload" on current Atlassian schema.
    body = {"cbAttachments": "true", "exportToCloud": "true"}

    resp = requests.post(url, headers=ui_headers(site), cookies=cookies,
                         json=body, timeout=60)

    if resp.status_code == 412:
        print(f"[COOLDOWN] {resp.text}")
        return None

    if resp.status_code == 403:
        body_text = resp.text
        if "only accessible from the UI" in body_text:
            print("[ERROR] Cookie auth rejected — cookies likely expired.",
                  file=sys.stderr)
            print("[HINT] Refresh JIRA_COOKIES in Jenkins Credentials.",
                  file=sys.stderr)
            sys.exit(2)
        print(f"[ERROR] 403 from runbackup: {body_text}", file=sys.stderr)
        sys.exit(1)

    resp.raise_for_status()

    # Print raw response on first runs to verify shape — task ID extraction
    # depends on it. Field name varies by endpoint version.
    print(f"[DEBUG] runbackup response: {resp.text}")
    return resp.json() if resp.text else {}


def get_last_task_id(site: str, cookies: dict) -> str | None:
    """Fallback if runbackup response doesn't include task ID directly."""
    url = f"{site}/rest/backup/1/export/lastTaskId"
    resp = requests.get(url, headers=ui_headers(site, for_get=True), cookies=cookies, timeout=30)
    if resp.status_code != 200:
        return None
    return resp.text.strip().strip('"') or None


def poll_progress(site: str, cookies: dict, task_id: str,
                  timeout_sec: int = 21600, interval_sec: int = 30) -> dict:
    """
    GET /rest/backup/1/export/getProgress?taskId={taskId}
    Returns final response dict when backup is complete.
    """
    url = f"{site}/rest/backup/1/export/getProgress"
    headers = ui_headers(site, for_get=True)

    deadline = time.time() + timeout_sec
    poll_count = 0

    while time.time() < deadline:
        poll_count += 1
        resp = requests.get(
            url,
            headers=headers,
            cookies=cookies,
            params={"taskId": task_id, "_": str(int(time.time() * 1000))},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        progress = data.get("progress", 0)
        status = data.get("status", data.get("currentStatus", ""))
        ui.info(f"[poll {poll_count}] progress={progress}% status={status}")

        # Backup complete when 'result' field appears (download fileId)
        if data.get("result"):
            return data

        time.sleep(interval_sec)

    raise TimeoutError(f"Backup did not complete within {timeout_sec}s")


def download_backup(site: str, cookies: dict, download_ref: str, out_path: Path,
                    show_progress: bool = False) -> int:
    """
    Stream the export to disk. `download_ref` is either:
      - a full URL (modern Jira Cloud returns an api.media.atlassian.com URL whose
        token is embedded — fetched directly, no cookies), or
      - a fileId for the legacy `/plugins/servlet/export/download/?fileId=` servlet.
    Returns bytes written.
    """
    ref = str(download_ref)
    if ref.startswith(("http://", "https://")):
        url, req_kwargs = ref, {"headers": {"User-Agent": USER_AGENT}}
    else:
        # The completion `result` field is `<uuid>/binary`, but the download servlet
        # expects only the bare `<uuid>` (the browser uses
        # `?fileId=<uuid>`, no `/binary`). Passing the `/binary` suffix yields a
        # malformed media URL and a 404. Strip everything from the first slash.
        file_id = ref.split("/", 1)[0]
        url = f"{site}/plugins/servlet/export/download/"
        req_kwargs = {"headers": {"User-Agent": USER_AGENT}, "cookies": cookies,
                      "params": {"fileId": file_id}}

    bytes_written = 0
    with requests.get(url, stream=True, timeout=600, **req_kwargs) as resp:
        if resp.status_code >= 400:
            snippet = ""
            try:
                snippet = " ".join((resp.text or "").split())[:300]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                f"Download failed: HTTP {resp.status_code} from {resp.url}\n"
                f"  body: {snippet}\n"
                f"  Modern Jira Cloud serves exports from api.media.atlassian.com; the "
                f"download reference may need different handling. Capture the browser's "
                f"'Copy as cURL' of a manual export download and share it so this can be fixed.")
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


def test_connection(site: str, cookie_blob: str) -> tuple[bool, str]:
    """Non-exiting check: cookies present + session live + JWT expiry hint."""
    cookies = cookies_from_blob(cookie_blob)
    missing = missing_cookies(cookies)
    if missing:
        return False, f"Missing required cookies: {missing}"

    days = session_token_days_left(cookies)
    note = f"; session token ~{days:.0f}d left" if days is not None else ""
    if days is not None and days < 0:
        return False, f"Session token expired{note} — refresh cookies"

    try:
        resp = requests.get(f"{site}/rest/backup/1/export/lastTaskId",
                            headers=ui_headers(site, for_get=True), cookies=cookies,
                            timeout=30)
    except requests.RequestException as exc:
        return False, f"Request failed: {exc}"

    # 200 = a prior task id is returned; 204 = authenticated but no backup run
    # yet (no last task). Both mean the cookies are valid.
    if resp.status_code in (200, 204):
        extra = " — no previous backup task yet" if resp.status_code == 204 else ""
        return True, f"Jira cookies valid (HTTP {resp.status_code}{extra}){note}"

    body = " ".join((resp.text or "").split())[:200]
    if "only accessible from the UI" in (resp.text or ""):
        return False, (f"HTTP {resp.status_code}: Atlassian's UI-only gate rejected the "
                       f"request (not a cookie problem){note} — body: {body}")
    if resp.status_code in (401, 403):
        return False, (f"HTTP {resp.status_code} — likely expired/invalid cookies{note}; "
                       f"body: {body}")
    return False, f"Unexpected HTTP {resp.status_code}{note} — body: {body}"


def _download_from_task(site: str, cookies: dict, final: dict, out_dir: Path,
                        name_template: str, label: str) -> Path:
    """Resolve the download reference from a completed task response and stream it."""
    download_ref = (final.get("downloadUrl") or final.get("mediaUrl")
                    or final.get("result") or final.get("fileName"))
    if not download_ref:
        raise RuntimeError(f"No download reference in completion response: {final}")
    out_path = out_dir / naming.render_name(name_template, "jira", ext=".zip", site=site)
    size = download_backup(site, cookies, download_ref, out_path, show_progress=True)
    ui.ok(f"Jira backup{label}: {out_path} ({size / (1024 * 1024):.1f} MB)")
    return out_path


def fetch_existing_backup(site: str, cookies: dict, out_dir: Path,
                          name_template: str = naming.DEFAULT_PRODUCT_TEMPLATE,
                          poll_timeout: int = 21600) -> Path | None:
    """
    Download the most recent COMPLETED Jira backup WITHOUT triggering a new one.

    Used on cooldown (a fresh backup is blocked for 48h, but the previous one is
    usually still downloadable) and for reruns that just need to ship an existing
    backup. Returns the .zip path, or None when there is nothing to download.
    """
    task_id = get_last_task_id(site, cookies)
    if not task_id:
        ui.warn("No previous Jira backup task found — nothing to download")
        return None
    ui.info(f"Fetching most recent existing Jira backup (task {task_id})")
    try:
        final = poll_progress(site, cookies, str(task_id), timeout_sec=poll_timeout)
    except TimeoutError:
        ui.warn("Existing Jira backup task is still in progress — try again later")
        return None
    try:
        return _download_from_task(site, cookies, final, out_dir, name_template, " (existing)")
    except RuntimeError as exc:
        ui.warn(f"Existing Jira backup could not be downloaded (likely expired): {exc}")
        return None


def run_backup(site: str, cookies: dict, out_dir: Path,
               name_template: str = naming.DEFAULT_PRODUCT_TEMPLATE,
               poll_timeout: int = 21600,
               download_existing: bool = False) -> Path | None:
    """
    Full trigger→poll→download flow. Returns the .zip path, or None when there is
    nothing to download (cooldown with no prior backup).

    On 48h cooldown a NEW backup is blocked, so we fall back to downloading the
    most recent EXISTING backup — that way a (re)run still ships a Jira archive
    and the pipeline can continue. `download_existing=True` skips the trigger
    entirely and only fetches the latest existing backup.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    if download_existing:
        ui.info(f"Fetching existing Jira backup on {site} (no new trigger)")
        return fetch_existing_backup(site, cookies, out_dir,
                                     name_template=name_template,
                                     poll_timeout=poll_timeout)

    ui.info(f"Triggering Jira backup on {site}")
    trigger_result = trigger_backup(site, cookies)

    if trigger_result is None:
        ui.warn("Jira backup on 48h cooldown — falling back to the most recent existing backup")
        existing = fetch_existing_backup(site, cookies, out_dir,
                                         name_template=name_template,
                                         poll_timeout=poll_timeout)
        if existing is None:
            marker = out_dir / "jira_cooldown.txt"
            marker.write_text(
                f"Cooldown active at {datetime.now(timezone.utc).isoformat()}; "
                f"no existing backup available to download\n")
            ui.warn("Cooldown active and no existing backup to download — Jira skipped")
        return existing

    # Extract task ID — field name varies across endpoint versions.
    task_id = (trigger_result.get("taskId") or
               trigger_result.get("id") or
               trigger_result.get("result"))
    if not task_id:
        ui.info("No task ID in runbackup response, querying lastTaskId")
        task_id = get_last_task_id(site, cookies)
    if not task_id:
        raise RuntimeError(f"Cannot determine task ID. Raw response: {trigger_result}")

    ui.info(f"Polling progress (task {task_id})")
    final = poll_progress(site, cookies, str(task_id), timeout_sec=poll_timeout)
    # The download field varies by instance/version — log the full response so the
    # exact field can be confirmed if the download path needs adjusting.
    print(f"[DEBUG] completion response: {final}")

    return _download_from_task(site, cookies, final, out_dir, name_template, "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True,
                        help="Jira site root, e.g. https://<YOUR_SITE>.atlassian.net")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output directory for downloaded backup")
    parser.add_argument("--poll-timeout", type=int,
                        default=int(os.environ.get("POLL_TIMEOUT", "21600")),
                        help="Max seconds to wait for backup to complete "
                             "(default 21600 = 6h; env: POLL_TIMEOUT). Jira exports "
                             "can take minutes to several hours.")
    parser.add_argument("--name-template",
                        default=os.environ.get("PRODUCT_NAME_TEMPLATE",
                                               naming.DEFAULT_PRODUCT_TEMPLATE),
                        help="Filename template (tokens: {product}{site}{date}"
                             "{time}{datetime}{timestamp})")
    parser.add_argument("--download-existing", action="store_true",
                        default=os.environ.get("JIRA_DOWNLOAD_EXISTING", "").lower()
                        in ("1", "true", "yes"),
                        help="Skip triggering a new backup; download the most recent "
                             "existing Jira backup (useful on cooldown / reruns). "
                             "Env: JIRA_DOWNLOAD_EXISTING=true")
    args = parser.parse_args()

    cookie_blob = os.environ.get("JIRA_COOKIES")
    if not cookie_blob:
        sys.exit("JIRA_COOKIES env var not set — bind via Jenkins withCredentials")

    cookies = parse_cookie_blob(cookie_blob)
    try:
        run_backup(args.site, cookies, args.out,
                   name_template=args.name_template, poll_timeout=args.poll_timeout,
                   download_existing=args.download_existing)
    except (RuntimeError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
