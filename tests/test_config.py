"""Offline tests for backup.config — .env parsing + env precedence.

config.load() mutates os.environ via setdefault, so an autouse fixture snapshots
and restores os.environ around each test to keep them isolated.
"""
import os

import pytest

from backup import config


@pytest.fixture(autouse=True)
def restore_env():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_parse_env_file_handles_comments_blanks_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join([
            "# a comment",
            "",
            "SITE_JIRA=https://acme.atlassian.net",
            'ATL_EMAIL="quoted@example.com"',
            "ARCHIVE_PASSWORD='single quoted'",
            "  SPACED = value with spaces  ",
            "NOT_A_PAIR",
        ]),
        encoding="utf-8",
    )
    parsed = config.parse_env_file(env)
    assert parsed["SITE_JIRA"] == "https://acme.atlassian.net"
    assert parsed["ATL_EMAIL"] == "quoted@example.com"
    assert parsed["ARCHIVE_PASSWORD"] == "single quoted"
    assert parsed["SPACED"] == "value with spaces"
    assert "NOT_A_PAIR" not in parsed


def test_parse_env_file_missing_returns_empty(tmp_path):
    assert config.parse_env_file(tmp_path / "nope.env") == {}


def test_load_real_env_wins_over_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SITE_JIRA=https://from-dotenv.atlassian.net\n", encoding="utf-8")
    monkeypatch.setenv("SITE_JIRA", "https://from-real-env.atlassian.net")
    cfg = config.load(env_file=env)
    assert cfg.site_jira == "https://from-real-env.atlassian.net"


def test_load_reads_dotenv_when_env_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("STORAGE_DEST", raising=False)
    env = tmp_path / ".env"
    env.write_text("STORAGE_DEST=my-bucket\n", encoding="utf-8")
    cfg = config.load(env_file=env)
    assert cfg.storage_dest == "my-bucket"


def test_load_defaults_when_unset(tmp_path, monkeypatch):
    for key in ("STORAGE_PROVIDER", "FAILURE_POLICY", "ARCHIVE_MODE", "JIRA_COOLDOWN_ACTION"):
        monkeypatch.delenv(key, raising=False)
    cfg = config.load(env_file=tmp_path / "absent.env")
    assert cfg.storage_provider == "local"
    assert cfg.failure_policy == "balanced"
    assert cfg.archive_mode == "per-product"
    assert cfg.jira_cooldown_action == "download-existing"
