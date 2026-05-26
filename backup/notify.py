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


@dataclass
class BackupReport:
    status: str                       # "success" | "failure"
    timestamp: str
    archives: list[tuple[str, float]] = field(default_factory=list)  # (name, MB)
    build_url: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def icon(self) -> str:
        return "✅" if self.ok else "❌"

    def archive_lines(self) -> list[str]:
        return [f"{name} — {mb:.1f} MB" for name, mb in self.archives]

    def summary_text(self) -> str:
        """Plain-text body shared by slack/discord/teams/email/webhook."""
        lines = [
            f"{self.icon} Atlassian Weekly Backup — {self.status.upper()}",
            f"Time: {self.timestamp}",
        ]
        if self.archives:
            lines.append("Archives:")
            lines += [f"  • {ln}" for ln in self.archive_lines()]
        else:
            lines.append("Archives: (none found)")
        if self.build_url:
            lines.append(f"Build: {self.build_url}")
        return "\n".join(lines)


def build_report(status: str, archive_dir: Path, build_url: str) -> BackupReport:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    archives: list[tuple[str, float]] = []
    if archive_dir.exists():
        for a in sorted(archive_dir.glob("*.7z")):
            archives.append((a.name, a.stat().st_size / (1024 * 1024)))
    return BackupReport(status=status, timestamp=now,
                        archives=archives, build_url=build_url)


# ── Channel renderers — each raises on failure, returns None on success ──

def _post_json(url: str, payload: dict) -> None:
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")


def send_google_chat(report: BackupReport, url: str) -> None:
    widgets = [
        {"decoratedText": {"topLabel": "Status",
                           "text": f"<b>{report.icon} {report.status.upper()}</b>"}},
        {"decoratedText": {"topLabel": "Timestamp", "text": report.timestamp}},
    ]
    if report.archives:
        widgets.append({"decoratedText": {
            "topLabel": "Archives",
            "text": "<br>".join(report.archive_lines()), "wrapText": True}})
    if report.build_url:
        widgets.append({"buttonList": {"buttons": [
            {"text": "View build logs",
             "onClick": {"openLink": {"url": report.build_url}}}]}})
    _post_json(url, {"cardsV2": [{"cardId": "atlassian-backup-status", "card": {
        "header": {"title": "Atlassian Weekly Backup",
                   "subtitle": f"Status: {report.status}"},
        "sections": [{"widgets": widgets}]}}]})


def send_slack(report: BackupReport, url: str) -> None:
    _post_json(url, {"text": report.summary_text()})


def send_discord(report: BackupReport, url: str) -> None:
    fields = [{"name": "Status", "value": f"{report.icon} {report.status.upper()}",
               "inline": True},
              {"name": "Time", "value": report.timestamp, "inline": True}]
    if report.archives:
        fields.append({"name": "Archives",
                       "value": "\n".join(report.archive_lines())})
    embed = {"title": "Atlassian Weekly Backup",
             "color": 0x0F9D58 if report.ok else 0xDB4437,
             "fields": fields}
    if report.build_url:
        embed["url"] = report.build_url
    _post_json(url, {"embeds": [embed]})


def send_teams(report: BackupReport, url: str) -> None:
    facts = [{"name": "Status", "value": f"{report.icon} {report.status.upper()}"},
             {"name": "Time", "value": report.timestamp}]
    if report.archives:
        facts.append({"name": "Archives", "value": "; ".join(report.archive_lines())})
    card = {
        "@type": "MessageCard", "@context": "http://schema.org/extensions",
        "themeColor": "0F9D58" if report.ok else "DB4437",
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
        "archives": [{"name": n, "size_mb": round(mb, 1)} for n, mb in report.archives],
        "build_url": report.build_url,
        "text": report.summary_text(),
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
    msg["Subject"] = f"{report.icon} Atlassian Backup — {report.status.upper()}"
    msg["From"] = sender
    msg["To"] = recipients
    msg.set_content(report.summary_text())

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
    parser.add_argument("--status", required=True, choices=["success", "failure"])
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
