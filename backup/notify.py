"""
Send a backup status notification to one or more channels.

A single neutral report (status, timestamp, archive sizes, build URL) is built
once, then rendered per selected channel. Pick channels with --channels:

  google-chat   Google Chat incoming webhook  (cardsV2)
  slack         Slack incoming webhook         (mrkdwn text)
  discord       Discord webhook                (embed)
  teams         Microsoft Teams webhook        (legacy MessageCard)
  email         SMTP                           (stdlib smtplib, no dep)
  webhook       Generic POST of the raw report JSON (PagerDuty/Opsgenie/custom)

Webhook-based channels share one URL from --webhook-url or NOTIFY_WEBHOOK_URL.
Email uses SMTP_* env vars. No third-party dependencies beyond `requests`.
"""
import argparse
import os
import smtplib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import requests

from . import jira, manifest

# Warn in the notification when the Jira session cookie is within this many days
# of expiry, so operators refresh it before a backup fails.
COOKIE_WARN_DAYS = 7


@dataclass
class BackupReport:
    status: str                       # "success" | "unstable" | "failure"
    timestamp: str
    date: str = ""                    # YYYY-MM-DD
    archives: list[tuple[str, float]] = field(default_factory=list)  # (name, MB)
    products: list[str] = field(default_factory=list)                # e.g. ["jira"]
    build_url: str = ""
    warnings: list[str] = field(default_factory=list)
    subject_template: str = ""        # NOTIFY_SUBJECT_TEMPLATE (blank = default)
    body_template: str = ""           # NOTIFY_BODY_TEMPLATE (blank = default)

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def unstable(self) -> bool:
        return self.status == "unstable"

    @property
    def icon(self) -> str:
        if self.ok:
            return "✅"
        if self.unstable:
            return "⚠️"
        return "❌"

    @property
    def color_int(self) -> int:
        """Discord embed color: green / amber / red."""
        return 0x0F9D58 if self.ok else (0xF4B400 if self.unstable else 0xDB4437)

    @property
    def color_hex(self) -> str:
        """Teams themeColor: green / amber / red."""
        return "0F9D58" if self.ok else ("F4B400" if self.unstable else "DB4437")

    @property
    def count(self) -> int:
        return len(self.archives)

    @property
    def total_mb(self) -> float:
        return sum(mb for _, mb in self.archives)

    @property
    def products_str(self) -> str:
        return ", ".join(self.products) if self.products else "—"

    @property
    def size_str(self) -> str:
        return f"{self.total_mb:.1f} MB"

    def archive_lines(self) -> list[str]:
        return [f"{name} — {mb:.1f} MB" for name, mb in self.archives]

    def _tokens(self) -> dict:
        """Placeholders for NOTIFY_SUBJECT_TEMPLATE / NOTIFY_BODY_TEMPLATE."""
        return {
            "{status}": self.status,
            "{icon}": self.icon,
            "{date}": self.date,
            "{time}": self.timestamp,
            "{products}": self.products_str,
            "{count}": str(self.count),
            "{size}": self.size_str,
            "{archives}": "; ".join(self.archive_lines()) or "(none)",
            "{build_url}": self.build_url,
            "{warnings}": "; ".join(self.warnings) or "(none)",
        }

    def _render(self, template: str) -> str:
        out = template
        for token, value in self._tokens().items():
            out = out.replace(token, value)
        return out

    def subject(self) -> str:
        """Email subject: NOTIFY_SUBJECT_TEMPLATE if set, else the default."""
        if self.subject_template:
            return self._render(self.subject_template)
        return f"{self.icon} Atlassian Backup — {self.status.upper()} ({self.date})"

    def body(self) -> str:
        """Message body: NOTIFY_BODY_TEMPLATE if set, else the default summary."""
        if self.body_template:
            return self._render(self.body_template)
        return self.summary_text()

    def summary_text(self) -> str:
        """Default plain-text body (used when NOTIFY_BODY_TEMPLATE is unset)."""
        lines = [
            f"{self.icon} Atlassian Weekly Backup — {self.status.upper()}",
            f"Time: {self.timestamp}",
            f"Products: {self.products_str}",
        ]
        if self.archives:
            lines.append("Archives:")
            lines += [f"  • {ln}" for ln in self.archive_lines()]
            lines.append(f"Total: {self.count} file(s), {self.size_str}")
        else:
            lines.append("Archives: (none found)")
        if self.build_url:
            lines.append(f"Build: {self.build_url}")
        for w in self.warnings:
            lines.append(f"WARNING: {w}")
        return "\n".join(lines)


def _cookie_warnings() -> list[str]:
    """Warn if the Jira session cookie (from JIRA_COOKIES env) is near expiry."""
    blob = os.environ.get("JIRA_COOKIES", "")
    if not blob:
        return []
    days = jira.session_token_days_left(jira.cookies_from_blob(blob))
    if days is None:
        return []
    if days < 0:
        return ["Jira session cookie has EXPIRED — refresh JIRA_COOKIES."]
    if days < COOKIE_WARN_DAYS:
        return [f"Jira session cookie expires in ~{days:.0f} day(s) — refresh it soon."]
    return []


def build_report(status: str, archive_dir: Path, build_url: str) -> BackupReport:
    now = datetime.now(timezone.utc)
    archives: list[tuple[str, float]] = []
    if archive_dir.exists():
        for a in sorted(archive_dir.glob("*.7z")):
            archives.append((a.name, a.stat().st_size / (1024 * 1024)))
    # Products: prefer the manifests' recorded products; fall back to inferring
    # from the archive filenames.
    products: list[str] = []
    for man in manifest.read_all(archive_dir):
        for p in man.get("products", []):
            if p not in products:
                products.append(p)
    if not products:
        for name, _ in archives:
            for p in ("jira", "confluence"):
                if p in name.lower() and p not in products:
                    products.append(p)
    return BackupReport(
        status=status,
        timestamp=now.strftime("%Y-%m-%d %H:%M UTC"),
        date=now.strftime("%Y-%m-%d"),
        archives=archives,
        products=products,
        build_url=build_url,
        warnings=_cookie_warnings(),
        subject_template=os.environ.get("NOTIFY_SUBJECT_TEMPLATE", ""),
        body_template=os.environ.get("NOTIFY_BODY_TEMPLATE", ""),
    )


# ── Channel renderers — each raises on failure, returns None on success ──

def _post_json(url: str, payload: dict) -> None:
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")


def send_google_chat(report: BackupReport, url: str) -> None:
    widgets = [
        {"decoratedText": {"topLabel": "Status",
                           "text": f"<b>{report.icon} {report.status.upper()}</b>"}},
        {"decoratedText": {"topLabel": "Date", "text": report.timestamp}},
        {"decoratedText": {"topLabel": "Products", "text": report.products_str}},
    ]
    if report.archives:
        widgets.append({"decoratedText": {
            "topLabel": f"Archives ({report.count}, {report.size_str})",
            "text": "<br>".join(report.archive_lines()), "wrapText": True}})
    for w in report.warnings:
        widgets.append({"decoratedText": {"topLabel": "Warning",
                                          "text": f"<b>⚠ {w}</b>", "wrapText": True}})
    if report.build_url:
        widgets.append({"buttonList": {"buttons": [
            {"text": "View build logs",
             "onClick": {"openLink": {"url": report.build_url}}}]}})
    _post_json(url, {"cardsV2": [{"cardId": "atlassian-backup-status", "card": {
        "header": {"title": "Atlassian Weekly Backup",
                   "subtitle": f"Status: {report.status}"},
        "sections": [{"widgets": widgets}]}}]})


def send_slack(report: BackupReport, url: str) -> None:
    _post_json(url, {"text": report.body()})


def send_discord(report: BackupReport, url: str) -> None:
    fields = [{"name": "Status", "value": f"{report.icon} {report.status.upper()}",
               "inline": True},
              {"name": "Date", "value": report.timestamp, "inline": True},
              {"name": "Products", "value": report.products_str, "inline": True}]
    if report.archives:
        fields.append({"name": f"Archives ({report.count}, {report.size_str})",
                       "value": "\n".join(report.archive_lines())})
    if report.warnings:
        fields.append({"name": "⚠ Warning", "value": "\n".join(report.warnings)})
    embed = {"title": "Atlassian Weekly Backup",
             "color": report.color_int,
             "fields": fields}
    if report.build_url:
        embed["url"] = report.build_url
    _post_json(url, {"embeds": [embed]})


def send_teams(report: BackupReport, url: str) -> None:
    facts = [{"name": "Status", "value": f"{report.icon} {report.status.upper()}"},
             {"name": "Date", "value": report.timestamp},
             {"name": "Products", "value": report.products_str}]
    if report.archives:
        facts.append({"name": f"Archives ({report.count}, {report.size_str})",
                      "value": "; ".join(report.archive_lines())})
    if report.warnings:
        facts.append({"name": "Warning", "value": "; ".join(report.warnings)})
    card = {
        "@type": "MessageCard", "@context": "http://schema.org/extensions",
        "themeColor": report.color_hex,
        "summary": "Atlassian Weekly Backup",
        "sections": [{"activityTitle": "Atlassian Weekly Backup", "facts": facts}],
    }
    if report.build_url:
        card["potentialAction"] = [{
            "@type": "OpenUri", "name": "View build logs",
            "targets": [{"os": "default", "uri": report.build_url}]}]
    _post_json(url, card)


def send_webhook(report: BackupReport, url: str) -> None:
    """Generic: POST the raw report so custom systems can parse it."""
    _post_json(url, {
        "status": report.status,
        "timestamp": report.timestamp,
        "date": report.date,
        "products": report.products,
        "count": report.count,
        "total_size_mb": round(report.total_mb, 1),
        "archives": [{"name": n, "size_mb": round(mb, 1)} for n, mb in report.archives],
        "build_url": report.build_url,
        "warnings": report.warnings,
        "text": report.body(),
    })


def send_email(report: BackupReport, _url: str) -> None:
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    recipients = os.environ.get("SMTP_TO", "")
    if not host or not sender or not recipients:
        raise RuntimeError("email channel needs SMTP_HOST, SMTP_FROM, SMTP_TO")

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    use_starttls = os.environ.get("SMTP_STARTTLS", "true").lower() != "false"

    msg = EmailMessage()
    msg["Subject"] = report.subject()
    msg["From"] = sender
    msg["To"] = recipients
    msg.set_content(report.body())

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            if user and password:
                s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if use_starttls:
                s.starttls()
            if user and password:
                s.login(user, password)
            s.send_message(msg)


WEBHOOK_CHANNELS = {
    "google-chat": send_google_chat,
    "slack": send_slack,
    "discord": send_discord,
    "teams": send_teams,
    "webhook": send_webhook,
}
CHANNELS = {**WEBHOOK_CHANNELS, "email": send_email}


def dispatch(channels: list[str], report: "BackupReport", webhook_url: str) -> int:
    """Send the report to each channel. Returns the number of failures."""
    failures = 0
    for channel in channels:
        if channel in WEBHOOK_CHANNELS and not webhook_url:
            print(f"[SKIP] {channel}: no webhook URL set "
                  "(--webhook-url / NOTIFY_WEBHOOK_URL)", file=sys.stderr)
            failures += 1
            continue
        try:
            CHANNELS[channel](report, webhook_url)
            print(f"[OK] notified: {channel}")
        except Exception as exc:  # report and continue to next channel
            print(f"[ERROR] {channel} failed: {exc}", file=sys.stderr)
            failures += 1
    return failures


def main():
    parser = argparse.ArgumentParser(description="Send backup status to channels")
    parser.add_argument("--channels", required=True,
                        help=f"Comma list of: {','.join(sorted(CHANNELS))}")
    parser.add_argument("--status", required=True,
                        choices=["success", "unstable", "failure"])
    parser.add_argument("--archive-dir", type=Path, default=Path("./archive"))
    parser.add_argument("--build-url", default="")
    parser.add_argument("--webhook-url", default=os.environ.get("NOTIFY_WEBHOOK_URL", ""),
                        help="URL for webhook-based channels (env NOTIFY_WEBHOOK_URL)")
    args = parser.parse_args()

    selected = [c.strip() for c in args.channels.split(",") if c.strip()]
    unknown = [c for c in selected if c not in CHANNELS]
    if unknown:
        sys.exit(f"Unknown channel(s): {unknown}. Valid: {sorted(CHANNELS)}")

    report = build_report(args.status, args.archive_dir, args.build_url)
    failures = dispatch(selected, report, args.webhook_url)
    if failures:
        sys.exit(f"{failures} channel(s) failed")


if __name__ == "__main__":
    main()
