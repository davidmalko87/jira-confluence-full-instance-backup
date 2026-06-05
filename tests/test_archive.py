"""Offline tests for backup.archive — pure-Python py7zr packing + encryption.

Verifies the .7z archives round-trip byte-identically (store + LZMA2), that an
encrypted archive is genuinely unreadable without the password (header
encryption hides the filenames too), and that per-product mode emits one .7z +
manifest per product and the manifests validate.
"""
import py7zr
import pytest
from py7zr.exceptions import PasswordRequired

from backup import archive, manifest


def _zip(path, data):
    path.write_bytes(data)
    return data


def _extract(arc, dest, password=None):
    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(arc, "r", password=password) as z:
        names = z.getnames()
        z.extractall(path=dest)
    return names


def test_archive_file_store_roundtrip(tmp_path):
    src = tmp_path / "jira-2026-06-06.zip"
    data = _zip(src, b"PK\x03\x04store-me-verbatim")
    arc = tmp_path / "jira-2026-06-06.7z"
    size = archive.archive_file(src, arc, password="", level=0)
    assert arc.exists() and size > 0
    names = _extract(arc, tmp_path / "x")
    assert names == ["jira-2026-06-06.zip"]                     # stored at basename
    assert (tmp_path / "x" / "jira-2026-06-06.zip").read_bytes() == data


def test_archive_file_compressed_roundtrip(tmp_path):
    src = tmp_path / "c.zip"
    data = _zip(src, b"PK\x03\x04" + b"A" * 5000)              # compressible
    arc = tmp_path / "c.7z"
    archive.archive_file(src, arc, password="", level=5)
    _extract(arc, tmp_path / "x")
    assert (tmp_path / "x" / "c.zip").read_bytes() == data


def test_archive_encrypted_unreadable_without_password(tmp_path):
    src = tmp_path / "e.zip"
    data = _zip(src, b"PK\x03\x04top-secret")
    arc = tmp_path / "e.7z"
    archive.archive_file(src, arc, password="s3cret", level=0)
    with pytest.raises(PasswordRequired):
        _extract(arc, tmp_path / "no")                         # header-encrypted
    _extract(arc, tmp_path / "yes", password="s3cret")
    assert (tmp_path / "yes" / "e.zip").read_bytes() == data


def test_run_archive_per_product_with_manifests(tmp_path):
    in_dir = tmp_path / "out"
    in_dir.mkdir()
    _zip(in_dir / "jira-2026-06-06.zip", b"PK\x03\x04jira-data")
    _zip(in_dir / "confluence-2026-06-06.zip", b"PK\x03\x04conf-data")
    arc_dir = tmp_path / "archive"
    archives = archive.run_archive(in_dir, arc_dir, password="pw", level=1, mode="per-product")
    assert len(archives) == 2
    for a in archives:
        assert a.suffix == ".7z" and a.exists()
        assert (arc_dir / f"{a.stem}{manifest.MANIFEST_SUFFIX}").exists()
    ok, issues = manifest.validate(arc_dir)
    assert ok, issues
