"""Offline tests for backup.naming — deterministic filename templates."""
from datetime import datetime, timezone

import pytest

from backup import naming

DT = datetime(2026, 5, 26, 1, 2, 3, tzinfo=timezone.utc)


def test_default_product_name():
    out = naming.render_name("{product}-{date}", "jira", ext=".zip", dt=DT)
    assert out == "jira-2026-05-26.zip"


def test_default_archive_name():
    out = naming.render_name("atlassian-backup-{date}", "atlassian", ext=".7z", dt=DT)
    assert out == "atlassian-backup-2026-05-26.7z"


def test_all_time_tokens_render_deterministically():
    tmpl = "{product}_{date}_{time}_{datetime}_{timestamp}_{year}-{month}-{day}"
    out = naming.render_name(tmpl, "jira", dt=DT)
    assert out == (
        f"jira_2026-05-26_010203_2026-05-26_010203_{int(DT.timestamp())}_2026-05-26"
    )


def test_site_token():
    out = naming.render_name("{product}-{site}-{date}", "jira",
                             site="https://acme.atlassian.net/wiki", dt=DT)
    assert out == "jira-acme-2026-05-26"


@pytest.mark.parametrize("site,slug", [
    ("https://acme.atlassian.net/wiki", "acme"),
    ("https://acme.atlassian.net", "acme"),
    ("acme.atlassian.net", "acme"),
    ("", "site"),
    (None, "site"),
])
def test_site_slug(site, slug):
    assert naming.site_slug(site) == slug


def test_unknown_token_raises_valueerror():
    with pytest.raises(ValueError) as exc:
        naming.render_name("{bogus}-{date}", "jira", dt=DT)
    assert "bogus" in str(exc.value)
