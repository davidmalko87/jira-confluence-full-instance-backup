"""Offline tests for backup.manifest — export validity + sha256 integrity.

Phase 3 hardening: verify_export must REJECT downloads that are not a real
export — HTML error/login pages (Atlassian serves HTML to non-browser UAs),
truncated/garbage files, corrupt ZIPs, and empty ZIPs — while ACCEPTING genuine
exports (and only WARNING on a valid ZIP that lacks a product's expected
entries). Also round-trips the manifest sha256 + validate().
"""
import hashlib
import io
import zipfile

from backup import manifest


def _zip_bytes(entries, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---- verify_export REJECTS things that are NOT a real export ----

def test_verify_rejects_html_login_page(tmp_path):
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(b"<!DOCTYPE html><html><body>Log in to continue</body></html>")
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is False
    assert "not a ZIP" in msg


def test_verify_rejects_empty_file(tmp_path):
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(b"")
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is False
    assert "not a ZIP" in msg


def test_verify_rejects_truncated_zip(tmp_path):
    # A real zip with its tail (central directory / EOCD) cut off -> not a zip.
    good = _zip_bytes({"entities.xml": b"<x/>", "activeobjects.xml": b"<y/>"})
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(good[: len(good) // 2])
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is False
    assert "not a ZIP" in msg


def test_verify_rejects_corrupt_entry(tmp_path):
    # Structurally valid zip (is_zipfile True) but an entry's data is corrupted,
    # so testzip() flags it -> the "corrupt entry" branch (a partial download
    # that still has an intact central directory).
    raw = bytearray(_zip_bytes({"data.bin": b"A" * 400}, compression=zipfile.ZIP_STORED))
    raw[80] ^= 0xFF                       # flip a byte well inside the stored data
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(bytes(raw))
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is False
    assert "corrupt" in msg.lower()


def test_verify_rejects_empty_zip(tmp_path):
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(_zip_bytes({}))
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is False
    assert "empty" in msg.lower()


# ---- verify_export ACCEPTS genuine exports ----

def test_verify_accepts_jira_with_markers(tmp_path):
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(_zip_bytes({"entities.xml": b"<x/>", "activeobjects.xml": b"<y/>"}))
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is True
    assert "valid jira export" in msg
    assert not msg.startswith("WARNING")


def test_verify_warns_jira_without_markers(tmp_path):
    p = tmp_path / "jira-backup.zip"
    p.write_bytes(_zip_bytes({"readme.txt": b"hi", "data.csv": b"1,2,3"}))
    ok, msg = manifest.verify_export(p, "jira")
    assert ok is True                     # a valid ZIP is not rejected...
    assert msg.startswith("WARNING")      # ...but the missing markers are surfaced


def test_verify_accepts_confluence_multifile_zip(tmp_path):
    # Confluence Cloud Site_Backup.zip is a multi-file ZIP with no required entry.
    p = tmp_path / "confluence-backup.zip"
    p.write_bytes(_zip_bytes({f"f{i}.xml": b"<x/>" for i in range(5)}))
    ok, msg = manifest.verify_export(p, "confluence")
    assert ok is True
    assert "valid confluence export" in msg


# ---- sha256 + validate round-trip ----

def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "blob"
    data = b"some bytes" * 1000
    p.write_bytes(data)
    assert manifest.sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_validate_passes_for_intact_archive(tmp_path):
    src = tmp_path / "jira-2026-05-26.zip"
    src.write_bytes(_zip_bytes({"entities.xml": b"<x/>"}))
    archive = tmp_path / "jira-2026-05-26.7z"
    archive.write_bytes(b"fake-7z-payload")
    man = manifest.build_files([src], archive, site="https://acme.atlassian.net")
    manifest.write(man, tmp_path, name="jira-2026-05-26" + manifest.MANIFEST_SUFFIX)
    ok, issues = manifest.validate(tmp_path)
    assert ok is True, issues
    assert issues == []
    assert "jira" in man["products"]


def test_validate_detects_corrupted_archive(tmp_path):
    src = tmp_path / "jira-2026-05-26.zip"
    src.write_bytes(_zip_bytes({"entities.xml": b"<x/>"}))
    archive = tmp_path / "jira-2026-05-26.7z"
    archive.write_bytes(b"original-content")
    man = manifest.build_files([src], archive)
    manifest.write(man, tmp_path, name="jira-2026-05-26" + manifest.MANIFEST_SUFFIX)
    # Same length, different bytes -> size matches but sha256 does not.
    archive.write_bytes(b"0riginal-content")
    ok, issues = manifest.validate(tmp_path)
    assert ok is False
    assert any("sha256 mismatch" in i for i in issues)


def test_validate_no_manifest(tmp_path):
    ok, issues = manifest.validate(tmp_path)
    assert ok is False
    assert issues and "No manifest" in issues[0]
