"""Transactional email (Phase 4d).

Email verification needs a way to send mail. This is deliberately a thin
SMTP client rather than a provider SDK, because the directive also asks for
secrets to come from the platform, not a config file.

Behaviour when SMTP is not configured is the part worth stating plainly:
`send()` returns False and the caller says so. It does NOT claim an email
was sent, and it does not log the message as though it were delivered. In
development the link is logged so a tester can complete the flow, and
`ALLOW_DEV_MAIL=1` is required for even that, so a staging deploy cannot
accidentally print verification links to its log aggregator.

If SMTP delivery fails, verification does not silently pass: the user stays
unverified and the endpoint returns an error telling them to retry.
"""
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("nare")

VERIFY_SUBJECT = "Confirm your email address"
VERIFY_BODY = (
    "Confirm your email address for NARE & CO.\n\n"
    "Open this link to activate your account:\n"
    "{url}\n\n"
    "The link expires in {hours} hours. "
    "If you did not create an account, you can ignore this message.\n"
)


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip())


def dev_mail_allowed() -> bool:
    """Printing a verification link to the log is a dev-only affordance."""
    return os.getenv("ALLOW_DEV_MAIL", "").strip().lower() in ("1", "true", "yes", "on")


def build_verify_url(base_url, token):
    base = (base_url or "").rstrip("/")
    return f"{base}/api/verify-email?token={token}"


def send(to, subject, body):
    """Send one message. Returns True only if it was really handed off.

    Callers must treat False as "not delivered" — that is what keeps an
    unconfigured mailer from turning into a bypass of email verification.
    """
    if not smtp_configured():
        if dev_mail_allowed():
            logger.warning(
                "[dev mail, NOT SENT] to=%s subject=%s body=%s", to, subject, body
            )
        else:
            logger.error(
                "SMTP_HOST is not set; refusing to send '%s' to %s. "
                "Email cannot be delivered.", subject, to
            )
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.getenv("SMTP_FROM", "no-reply@nareandco.com")
        msg["To"] = to
        msg.set_content(body)
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(os.getenv("SMTP_HOST"), port, timeout=10) as s:
            if os.getenv("SMTP_STARTTLS", "1") not in ("0", "false", "False"):
                s.starttls()
            user = os.getenv("SMTP_USERNAME")
            password = os.getenv("SMTP_PASSWORD")
            if user and password:
                s.login(user, password)
            s.send_message(msg)
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        # Never log the password or the body; the body carries a live token.
        logger.error(f"Email delivery to {to} failed: {e}")
        return False


def send_verification(to, url, hours=24):
    return send(to, VERIFY_SUBJECT, VERIFY_BODY.format(url=url, hours=hours))
