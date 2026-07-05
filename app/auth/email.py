"""Transactional email delivery through the shared SMTP configuration."""

from email.message import EmailMessage
import smtplib
import ssl

from app.core.config import settings


def send_message(
    message: EmailMessage,
) -> None:
    """Send one message through the shared SMTP configuration."""

    if not settings.email_enabled:
        raise RuntimeError("SMTP is not configured.")

    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        client = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=15,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=15,
        )

    with client:
        client.ehlo()
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            client.starttls(
                context=context
            )
            client.ehlo()
        if settings.smtp_username:
            client.login(
                settings.smtp_username,
                settings.smtp_password,
            )
        client.send_message(
            message
        )


def send_password_reset_code(
    email: str,
    code: str,
    expires_minutes: int,
) -> None:
    """Send a one-time password reset code through configured SMTP."""

    message = EmailMessage()
    message["Subject"] = "TBana Stream password reset code"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "\n".join(
            [
                "A password reset was requested for your TBana Stream account.",
                "",
                f"Reset code: {code}",
                "",
                f"This code expires in {expires_minutes} minutes.",
                "If you did not request this, you can ignore this email.",
            ]
        )
    )

    send_message(
        message
    )


def send_feedback_email(
    recipient: str,
    feedback: dict,
) -> None:
    """Email one locally saved feedback submission."""

    message = EmailMessage()
    message["Subject"] = (
        f"[TBana Stream] {feedback['category']} - "
        f"{feedback['subject']}"
    )
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                f"Category: {feedback['category']}",
                f"User Email: {feedback['email']}",
                f"User Plan: {feedback['plan']}",
                f"App Version: {feedback['app_version']}",
                f"Date & Time: {feedback['created_at']}",
                f"Subject: {feedback['subject']}",
                "",
                "Description:",
                feedback["description"],
            ]
        )
    )

    send_message(
        message
    )
