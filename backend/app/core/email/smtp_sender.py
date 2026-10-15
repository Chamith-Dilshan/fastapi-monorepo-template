import html
import re
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.core.config import settings
from app.core.email.base import EmailSender
from app.core.logging import get_logger

logger = get_logger("app.email.smtp")


def _html_to_text(html_body: str) -> str:
    """Plain-text twin of the HTML body. Mail clients that don't render HTML
    use it, spam filters like seeing both, and it makes the message readable
    in tooling (Mailpit's API exposes it, which is what end-to-end tests
    read one-time codes from)."""
    text = re.sub(r"(?is)<(script|style|head).*?</\1>", "", html_body)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h[1-6])>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class SmtpEmailSender(EmailSender):
    """Delivery over plain SMTP — works with any provider's SMTP relay
    (including Resend's, SES, Postmark), and with Mailpit in development.
    Choosing it is purely configuration; nothing that sends an email knows
    which sender is behind the interface.
    """

    async def send(self, *, to: str, subject: str, html_body: str) -> None:
        message = EmailMessage()
        message["From"] = formataddr(
            (settings.EMAIL_FROM_NAME, settings.EMAIL_FROM_ADDRESS)
        )
        message["To"] = to
        message["Subject"] = subject
        message.set_content(_html_to_text(html_body))
        message.add_alternative(html_body, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=settings.SMTP_TLS,
                use_tls=settings.SMTP_SSL,
                timeout=10,
            )
        except Exception:
            # Same contract as ResendEmailSender: log everything for
            # Sentry/traces, then let the caller decide (OTPService swallows
            # delivery failures so they never change an HTTP response).
            logger.error("email_send_failed", to=to, subject=subject, exc_info=True)
            raise
        logger.info("email_sent", to=to, subject=subject)
