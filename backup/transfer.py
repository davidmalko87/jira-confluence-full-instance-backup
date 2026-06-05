"""
Resilient large-file HTTP download with resume + retry.

Atlassian export downloads (Jira 20 GB+, Confluence 10 GB+) stream over a single
HTTPS GET. When the transfer runs long — most often when CPU is throttled, e.g.
inside a CPU-capped container — an intermediary can close the connection before
the body is complete (urllib3 IncompleteRead / requests ChunkedEncodingError). A
single-shot download has no recovery, so the whole file is lost and the build
fails partway.

resilient_download() recovers by resuming with an HTTP Range request from the
bytes already on disk and retrying with linear backoff. The caller passes a URL
that re-issues a FRESH transfer each time it is hit (the Jira download servlet
302-redirects to a brand-new presigned media URL on every request), so resumes
are never tied to a stale signed link. If the origin ignores Range (returns 200
instead of 206), that attempt restarts from zero — still bounded by the retry
budget. Returns total bytes written.

Tunables (env overrides):
  BACKUP_DOWNLOAD_MAX_ATTEMPTS   total attempts before giving up   (default 8)
  BACKUP_DOWNLOAD_READ_TIMEOUT   seconds between bytes before a read timeout (120)
  BACKUP_DOWNLOAD_BACKOFF        base backoff seconds, scaled by attempt    (10)
"""
import http.client
import os
import time
from pathlib import Path

import requests
import urllib3
from urllib3.util.retry import Retry

from . import diskspace, ui

DEFAULT_MAX_ATTEMPTS = int(os.environ.get("BACKUP_DOWNLOAD_MAX_ATTEMPTS", "8"))
DEFAULT_READ_TIMEOUT = int(os.environ.get("BACKUP_DOWNLOAD_READ_TIMEOUT", "120"))
DEFAULT_BACKOFF = int(os.environ.get("BACKUP_DOWNLOAD_BACKOFF", "10"))

# Mid-stream failures we recover from by resuming. A truncated body surfaces as
# ChunkedEncodingError or ConnectionError (wrapping urllib3 ProtocolError /
# IncompleteRead); read timeouts surface as ReadTimeout/Timeout.
_TRANSIENT = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ReadTimeout,
    requests.exceptions.Timeout,
    urllib3.exceptions.ProtocolError,
    urllib3.exceptions.IncompleteRead,
    http.client.IncompleteRead,
)


def _full_size(resp, requested_range: bool):
    """Full file size from Content-Range (206) or Content-Length (plain 200)."""
    cr = resp.headers.get("Content-Range")        # e.g. "bytes 100-199/23456"
    if cr and "/" in cr:
        tail = cr.rsplit("/", 1)[-1].strip()
        if tail.isdigit():
            return int(tail)
    # On a 206 the Content-Length is only the remaining range, not the whole
    # file — trust it only when we did NOT ask for a range.
    if not requested_range:
        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit():
            return int(cl)
    return None


def _new_session() -> requests.Session:
    session = requests.Session()
    # urllib3 retries cover connect/handshake + retryable statuses only. read=0:
    # a truncated *body* (200/206 that ends early) is handled by our resume loop,
    # not by urllib3 — which would otherwise replay the whole GET from zero.
    adapter = requests.adapters.HTTPAdapter(max_retries=Retry(
        total=3, connect=3, read=0, backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    ))
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def resilient_download(url, out_path, *, headers=None, params=None, cookies=None,
                       show_progress=False, max_attempts=DEFAULT_MAX_ATTEMPTS,
                       read_timeout=DEFAULT_READ_TIMEOUT, backoff=DEFAULT_BACKOFF) -> int:
    """Download `url` to `out_path`, resuming on mid-stream connection drops.

    Returns bytes written. Raises RuntimeError on a non-retryable HTTP status or
    after exhausting `max_attempts`.
    """
    out_path = Path(out_path)
    base_headers = dict(headers or {})
    session = _new_session()

    total = None            # full file size once known
    precheck_done = False
    bar_cm = bar_update = None
    bytes_written = 0
    last_exc = None

    def _ensure_bar(seed: int):
        nonlocal bar_cm, bar_update
        if show_progress and bar_cm is None:
            bar_cm = ui.progress_bar(total, f"Downloading {out_path.name}")
            bar_update = bar_cm.__enter__()
            if seed:
                bar_update(seed)

    try:
        for attempt in range(1, max_attempts + 1):
            have = out_path.stat().st_size if out_path.exists() else 0
            req_headers = dict(base_headers)
            if have:
                req_headers["Range"] = f"bytes={have}-"

            try:
                with session.get(url, params=params, headers=req_headers,
                                 cookies=cookies, stream=True,
                                 timeout=(30, read_timeout)) as resp:
                    # Already have the whole file.
                    if resp.status_code == 416 and total and have >= total:
                        bytes_written = have
                        break

                    if resp.status_code >= 400:
                        retryable = (
                            resp.status_code in (408, 425, 429)
                            or resp.status_code >= 500
                            # 401/403 on a RESUME is usually a stale presigned URL;
                            # the next attempt re-resolves it. A clean-start 401/403
                            # is a real auth failure and falls through to raise.
                            or (resp.status_code in (401, 403) and have > 0)
                        )
                        if retryable and attempt < max_attempts:
                            last_exc = RuntimeError(f"HTTP {resp.status_code} (retryable)")
                            ui.warn(f"[download] {last_exc} — attempt {attempt}/{max_attempts}, "
                                    f"re-resolving URL")
                            time.sleep(min(backoff * attempt, 60))
                            continue
                        snippet = ""
                        try:
                            snippet = " ".join((resp.text or "").split())[:300]
                        except Exception:  # noqa: BLE001
                            pass
                        raise RuntimeError(
                            f"Download failed: HTTP {resp.status_code} from {resp.url}\n"
                            f"  body: {snippet}")

                    resumed = resp.status_code == 206
                    if total is None:
                        total = _full_size(resp, requested_range=bool(have))
                    if not precheck_done:
                        diskspace.precheck(out_path.parent, total or 0)
                        precheck_done = True

                    if have and not resumed:
                        # Origin ignored our Range — discard partial, restart clean.
                        ui.warn("[download] origin ignored Range — restarting from 0")
                        have = 0
                        mode = "wb"
                    elif have and resumed:
                        mode = "ab"
                    else:
                        mode = "wb"

                    _ensure_bar(have)
                    with open(out_path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                if bar_update:
                                    bar_update(len(chunk))

                # Response drained without raising — done if we have the whole file.
                final = out_path.stat().st_size
                if total is None or final >= total:
                    bytes_written = final
                    break
                last_exc = RuntimeError(f"short read {final}/{total} bytes")
                ui.warn(f"[download] {last_exc} — attempt {attempt}/{max_attempts}")
                time.sleep(min(backoff, 30))

            except _TRANSIENT as exc:
                last_exc = exc
                have = out_path.stat().st_size if out_path.exists() else 0
                pct = f" ({have * 100 // total}%)" if total else ""
                ui.warn(f"[download] connection dropped at {have / 1048576:.0f} MB{pct} — "
                        f"attempt {attempt}/{max_attempts}: {type(exc).__name__}")
                if attempt < max_attempts:
                    time.sleep(min(backoff * attempt, 60))
                continue
        else:
            raise RuntimeError(f"Download failed after {max_attempts} attempts: {last_exc}")
    finally:
        if bar_cm is not None:
            bar_cm.__exit__(None, None, None)
        session.close()

    return bytes_written
