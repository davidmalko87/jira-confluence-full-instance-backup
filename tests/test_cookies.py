"""Offline tests for backup.jira cookie handling — parse, validate, JWT expiry.

No secrets: JWTs here are synthetic (a base64url payload with a chosen `exp`,
dummy header/signature), never a real session token.
"""
import base64
import json
import time

from backup import jira


def test_cookies_from_blob_basic():
    assert jira.cookies_from_blob("a=1; b=2;  c=3 ") == {"a": "1", "b": "2", "c": "3"}


def test_cookies_from_blob_value_with_equals():
    out = jira.cookies_from_blob("tenant.session.token=ab.cd=ef; x=1")
    assert out["tenant.session.token"] == "ab.cd=ef"
    assert out["x"] == "1"


def test_missing_cookies():
    assert jira.missing_cookies({"atlassian.xsrf.token": "z"}) == ["tenant.session.token"]
    full = {"tenant.session.token": "j", "atlassian.xsrf.token": "z"}
    assert jira.missing_cookies(full) == []


def test_extract_cookie_blob_from_curl():
    curl = (
        "curl 'https://acme.atlassian.net/rest/backup/1/export/runbackup' "
        "-H 'accept: application/json' "
        "-b 'tenant.session.token=jwt; atlassian.xsrf.token=xsrf' "
        "--compressed"
    )
    assert jira.extract_cookie_blob(curl) == "tenant.session.token=jwt; atlassian.xsrf.token=xsrf"


def test_extract_cookie_blob_from_header():
    header = "Cookie: tenant.session.token=jwt; atlassian.xsrf.token=xsrf;"
    assert jira.extract_cookie_blob(header) == "tenant.session.token=jwt; atlassian.xsrf.token=xsrf"


def test_extract_cookie_blob_passthrough():
    assert jira.extract_cookie_blob("a=1; b=2") == "a=1; b=2"


def _jwt_with_exp(exp):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_session_token_days_left_future():
    cookies = {"tenant.session.token": _jwt_with_exp(time.time() + 10 * 86400)}
    days = jira.session_token_days_left(cookies)
    assert days is not None and 9.9 < days < 10.1


def test_session_token_days_left_expired():
    cookies = {"tenant.session.token": _jwt_with_exp(time.time() - 5 * 86400)}
    days = jira.session_token_days_left(cookies)
    assert days is not None and days < 0


def test_session_token_days_left_malformed():
    assert jira.session_token_days_left({"tenant.session.token": "not-a-jwt"}) is None
    assert jira.session_token_days_left({}) is None
