"""Offline tests for backup.upload — target parsing, backend registry, layout.

Includes an offline live-verify of the 'local' storage backend (no cloud SDK,
no network): it must create the directory and leave no probe residue.
"""
from datetime import datetime, timezone

import pytest

from backup import upload


def test_backends_registry():
    assert set(upload.BACKENDS) == {"gcs", "s3", "azure", "local"}


def test_parse_targets_single():
    assert upload.parse_targets("local", "./backups") == [("local", "./backups")]


def test_parse_targets_multi_aligned():
    assert upload.parse_targets("gcs,s3", "bucketA,bucketB") == [
        ("gcs", "bucketA"), ("s3", "bucketB")]


def test_parse_targets_no_provider_raises():
    with pytest.raises(RuntimeError, match="no storage provider"):
        upload.parse_targets("", "bucket")


def test_parse_targets_count_mismatch_raises():
    with pytest.raises(RuntimeError, match="mismatch"):
        upload.parse_targets("gcs,s3", "only-one")


def test_parse_targets_unknown_provider_raises():
    with pytest.raises(RuntimeError, match="unknown provider"):
        upload.parse_targets("dropbox", "bucket")


@pytest.mark.parametrize("layout,fmt", [
    ("year", "%Y"),
    ("year-month", "%Y/%m"),
    ("year-month-day", "%Y/%m/%d"),
])
def test_layout_prefix_known(layout, fmt):
    assert upload._layout_prefix(layout) == datetime.now(timezone.utc).strftime(fmt)


def test_layout_prefix_flat_is_empty():
    assert upload._layout_prefix("flat") == ""


def test_layout_prefix_unknown_falls_back_to_year_month():
    assert upload._layout_prefix("bogus") == datetime.now(timezone.utc).strftime("%Y/%m")


def test_local_backend_writable_no_residue(tmp_path):
    dest = tmp_path / "store"
    ok, msg = upload.test_storage("local", str(dest))
    assert ok is True
    assert "writable" in msg
    assert dest.is_dir()
    assert list(dest.iterdir()) == []        # probe file written then removed


def test_test_storage_unknown_provider():
    ok, msg = upload.test_storage("dropbox", "bucket")
    assert ok is False
    assert "unknown provider" in msg
