"""
Notification backends:
  1. Desktop notification (via libnotify / notify-send on Linux, osascript on macOS,
     win10toast / plyer on Windows)
  2. Email (SMTP with TLS)
"""

import logging
import platform
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# Desktop notification
# ---------------------------------------------------------------------------

def _notify_linux(title: str, body: str) -> None:
    try:
        subprocess.Popen(
            ["notify-send", "--icon=dialog-information", "--expire-time=15000", title, body],
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.warning("notify-send not found; desktop notification skipped.")


def _notify_macos(title: str, body: str) -> None:
    script = f'display notification "{body}" with title "{title}"'
    subprocess.Popen(["osascript", "-e", script], stderr=subprocess.DEVNULL)


def _notify_windows(title: str, body: str) -> None:
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=body, timeout=15)
    except ImportError:
        try:
            from win10toast import ToastNotifier  # type: ignore
            ToastNotifier().show_toast(title, body, duration=15, threaded=True)
        except ImportError:
            logger.warning("No desktop notification library found for Windows.")


def send_desktop_notification(title: str, body: str) -> None:
    if SYSTEM == "Linux":
        _notify_linux(title, body)
    elif SYSTEM == "Darwin":
        _notify_macos(title, body)
    elif SYSTEM == "Windows":
        _notify_windows(title, body)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(
    smtp_host: str,
    smtp_port: int,
    use_tls: bool,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.sendmail(from_addr, [to_addr], msg.as_bytes())
    logger.info("Summary email sent to %s", to_addr)


# ---------------------------------------------------------------------------
# Unified notify function
# ---------------------------------------------------------------------------

def notify(summary: dict, text_report: str, html_report: Optional[str], config: dict) -> None:
    """Dispatch notifications based on user config."""
    from tarcker.summarizer import _fmt_duration  # local import to avoid circular

    day_str = summary["day"].strftime("%d/%m/%Y")
    active = _fmt_duration(summary["active_s"])
    top_apps = ", ".join(a["app_name"] for a in summary["top_apps"][:3])

    # Desktop notification
    if config.get("desktop_notification", {}).get("enabled", True):
        title = f"Tarcker — Resumo {day_str}"
        body = f"Tempo ativo: {active}\nTop apps: {top_apps}"
        send_desktop_notification(title, body)
        logger.info("Desktop notification sent")

    # Email
    email_cfg = config.get("email", {})
    if email_cfg.get("enabled") and email_cfg.get("to_addr"):
        subject = f"Tarcker — Resumo do dia {day_str}"
        try:
            send_email(
                smtp_host=email_cfg["smtp_host"],
                smtp_port=int(email_cfg["smtp_port"]),
                use_tls=bool(email_cfg.get("use_tls", True)),
                username=email_cfg.get("username", ""),
                password=email_cfg.get("password", ""),
                from_addr=email_cfg.get("from_addr", email_cfg.get("username", "")),
                to_addr=email_cfg["to_addr"],
                subject=subject,
                text_body=text_report,
                html_body=html_report,
            )
        except Exception as exc:
            logger.error("Failed to send email: %s", exc)
