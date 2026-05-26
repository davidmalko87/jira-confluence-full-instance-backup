"""
Render backup/archive filenames from a user template.

Templates use {token} placeholders. Available tokens:

  {product}    jira | confluence | atlassian        (what is being backed up)
  {site}       site slug derived from the URL        (e.g. "acme" from acme.atlassian.net)
  {date}       UTC date                              YYYY-MM-DD
  {time}       UTC time                              HHMMSS
  {datetime}   UTC date+time                         YYYY-MM-DD_HHMMSS
  {timestamp}  UTC epoch seconds                     1748222400
  {year} {month} {day}                               zero-padded components

Defaults reproduce the original names:
  per-product : "{product}-{date}"        -> jira-2026-05-26.zip
  archive     : "atlassian-backup-{date}" -> atlassian-backup-2026-05-26.7z
"""
from datetime import datetime, timezone
from urllib.parse import urlparse

DEFAULT_PRODUCT_TEMPLATE = "{product}-{date}"
DEFAULT_ARCHIVE_TEMPLATE = "atlassian-backup-{date}"

_VALID_TOKENS = (
    "product", "site", "date", "time", "datetime", "timestamp",
    "year", "month", "day",
)


def site_slug(site: str | None) -> str:
    """'https://acme.atlassian.net/wiki' -> 'acme'. Empty/placeholder -> 'site'."""
    if not site:
        return "site"
    host = urlparse(site).netloc or site
    host = host.split(":")[0]                      # drop any port
    label = host.split(".")[0]                     # first DNS label
    label = label.strip("<>").strip()              # tolerate <YOUR_SITE> placeholder
    return label or "site"


def render_name(template: str, product: str, *, ext: str = "",
                site: str | None = None, dt: datetime | None = None) -> str:
    """Render a template into a filename. Raises ValueError on unknown tokens."""
    dt = dt or datetime.now(timezone.utc)
    values = {
        "product": product,
        "site": site_slug(site),
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H%M%S"),
        "datetime": dt.strftime("%Y-%m-%d_%H%M%S"),
        "timestamp": str(int(dt.timestamp())),
        "year": dt.strftime("%Y"),
        "month": dt.strftime("%m"),
        "day": dt.strftime("%d"),
    }
    try:
        name = template.format(**values)
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"Unknown token {exc} in name template '{template}'. "
            f"Valid tokens: {', '.join('{' + t + '}' for t in _VALID_TOKENS)}"
        ) from exc
    return f"{name}{ext}"
