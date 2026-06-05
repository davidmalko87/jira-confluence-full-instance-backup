"""
Tests for ``backup.transfer.resilient_download`` — the resumable, retrying
large-file downloader.

A real localhost HTTP server is used (no mocking, no network egress). It can:
  * honour HTTP Range requests (``206`` + ``Content-Range``), and
  * cut the connection mid-stream on the first hit,
so the tests prove the downloader resumes from the bytes already on disk and
ends with a byte-identical file. Standard library only, plus pytest.
"""
import hashlib
import http.server
import os
import socketserver
import threading

from backup import transfer

CHUNK = 8 * 1024 * 1024  # must match transfer's iter_content chunk size


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_handler(payload: bytes, *, drop_after=None, ignore_range=False):
    """Fresh handler subclass per test so the hit/range counters don't leak."""

    class _H(http.server.BaseHTTPRequestHandler):
        hits = 0
        ranges = []

        def log_message(self, *args):   # silence the default stderr logging
            pass

        def do_GET(self):
            cls = type(self)
            cls.hits += 1
            first = cls.hits == 1

            start = 0
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes=") and not ignore_range:
                start = int(rng.split("=", 1)[1].split("-", 1)[0])
            cls.ranges.append(start)

            body = payload[start:]
            if start and not ignore_range:
                self.send_response(206)
                self.send_header(
                    "Content-Range",
                    f"bytes {start}-{len(payload) - 1}/{len(payload)}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()

            if first and drop_after is not None:
                self.wfile.write(body[:drop_after])
                self.wfile.flush()
                self.connection.close()      # simulate a mid-stream drop
                return
            self.wfile.write(body)

    return _H


def _serve(handler_cls):
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _download(srv, out_path, **kwargs):
    port = srv.server_address[1]
    return transfer.resilient_download(
        f"http://127.0.0.1:{port}/export.bin", out_path,
        show_progress=False, backoff=0, **kwargs)   # backoff=0 → no sleeps


def test_clean_download(tmp_path):
    payload = os.urandom(3_000_000)
    handler = _make_handler(payload)
    srv = _serve(handler)
    try:
        out = tmp_path / "export.bin"
        written = _download(srv, out)
    finally:
        srv.shutdown()
    assert written == len(payload)
    assert _sha(out.read_bytes()) == _sha(payload)
    assert handler.hits == 1


def test_retry_after_midstream_drop(tmp_path):
    # Drop before a full chunk is flushed → the first attempt writes ~nothing,
    # the retry restarts from zero and completes.
    payload = os.urandom(3_000_000)
    handler = _make_handler(payload, drop_after=1_000_000)
    srv = _serve(handler)
    try:
        out = tmp_path / "export.bin"
        written = _download(srv, out)
    finally:
        srv.shutdown()
    assert written == len(payload)
    assert _sha(out.read_bytes()) == _sha(payload)
    assert handler.hits >= 2


def test_append_resume_via_range(tmp_path):
    # Payload spans multiple chunks; drop after >1 chunk so a partial file is on
    # disk. The resume must send a Range header and the server replies 206.
    payload = os.urandom(CHUNK * 3)               # 24 MB
    handler = _make_handler(payload, drop_after=CHUNK + 1_000_000)
    srv = _serve(handler)
    try:
        out = tmp_path / "export.bin"
        written = _download(srv, out)
    finally:
        srv.shutdown()
    assert written == len(payload)
    assert _sha(out.read_bytes()) == _sha(payload)
    assert any(r > 0 for r in handler.ranges)     # a Range/resume request was issued


def test_origin_ignoring_range_restarts(tmp_path):
    # Server drops mid-stream, then ignores Range on the retry (answers 200 with
    # the full body). The downloader must discard the partial and restart clean.
    payload = os.urandom(CHUNK * 2)               # 16 MB
    handler = _make_handler(payload, drop_after=CHUNK + 500_000, ignore_range=True)
    srv = _serve(handler)
    try:
        out = tmp_path / "export.bin"
        written = _download(srv, out)
    finally:
        srv.shutdown()
    assert written == len(payload)
    assert _sha(out.read_bytes()) == _sha(payload)
    assert handler.hits >= 2
