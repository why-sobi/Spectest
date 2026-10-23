"""Builds the test report email and sends it via SMTP (or writes it to an outbox when SMTP is not configured)."""
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from spectest.config import is_placeholder_email


def build_report(project_id, commit_sha, spec_version, total, passed, failed, analysis, repairs=(),
                 test_file="") -> tuple[str, str]:
    status = "PASS" if failed == 0 else "FAIL"
    fixed = f", {sum(len(r['tests']) for r in repairs)} test(s) repaired" if repairs else ""
    subject = f"[SpecTest] {project_id} @ {commit_sha[:12]}: {status} ({passed}/{total} passed{fixed})"
    body = (
        f"Project ID:   {project_id}\n"
        f"Commit SHA:   {commit_sha}\n"
        f"Spec version: v{spec_version}\n"
        f"Total tests:  {total}\n"
        f"Passed:       {passed}\n"
        f"Failed:       {failed}\n"
    )
    if analysis:
        body += f"\nDiagnosis (SpecTest investigator):\n{analysis}\n"
    if repairs:
        body += f"\nTests repaired by the agent (please review {test_file}):\n"
        for r in repairs:
            body += f"- {', '.join(r['tests'])}: {r['reason']}\n  Spec: \"{r['spec_quote']}\"\n"
    return subject, body


class SMTPConfigError(RuntimeError):
    pass


def smtp_settings() -> tuple[str, int, str, str]:
    host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    if "@" in host:
        raise SMTPConfigError(f"SMTP_HOST should be a mail server such as smtp.gmail.com, not an email address ({host})")
    try:
        port = int(os.getenv("SMTP_PORT") or 587)
    except ValueError:
        raise SMTPConfigError("SMTP_PORT must be a number (587 for Gmail)")
    user, password = os.getenv("SMTP_USER", "").strip(), os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    if not user or not password:
        raise SMTPConfigError("SMTP_USER and SMTP_PASSWORD must both be set")
    return host, port, user, password  # App Passwords are shown with spaces; Gmail accepts them without


APP_PASSWORD_HINT = ("Gmail needs an App Password, not your normal password: turn on 2-Step Verification, then "
                     "create one at https://myaccount.google.com/apppasswords (16 letters). School/work accounts: "
                     "your admin may have disabled App Passwords; use a personal Gmail as SMTP_USER instead.")


def smtp_login(user: str, password: str, host: str, port: int):
    """Open an authenticated connection (caller closes it)."""
    smtp = (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)(host, port, timeout=30)
    try:
        if port != 465:
            smtp.starttls()
        smtp.login(user, password)
        return smtp
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected) as e:
        smtp.close()
        if isinstance(e, smtplib.SMTPAuthenticationError):
            detail = e.smtp_error.decode(errors="replace")[:200]
        else:  # Gmail often just drops the connection when given a normal account password
            detail = "server closed the connection during login"
        hint = APP_PASSWORD_HINT if "gmail" in host.lower() else "check SMTP_USER and SMTP_PASSWORD."
        raise SMTPConfigError(f"login rejected for {user} ({detail}). {hint}")


def send_smtp(msg: MIMEText):
    host, port, user, password = smtp_settings()
    smtp = smtp_login(user, password, host, port)
    try:
        smtp.send_message(msg)
    finally:
        smtp.quit()


def send_report(to_addr: str, subject: str, body: str, outbox: Path) -> str:
    """Returns 'smtp' or 'outbox' depending on how the report was delivered."""
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user or "spectest@localhost", to_addr

    if user and password and not is_placeholder_email(to_addr):
        send_smtp(msg)
        return "smtp"

    outbox.mkdir(parents=True, exist_ok=True)
    (outbox / f"{datetime.now():%Y%m%d-%H%M%S-%f}.eml").write_text(msg.as_string(), encoding="utf-8")
    return "outbox"
