import resend

from app.core.config import settings
from app.core.email.base import EmailSender
from app.core.logging import get_logger

logger = get_logger("app.email.resend")


class ResendEmailSender(EmailSender):
    """Real delivery via Resend's HTTP API, using the SDK's own
    `send_async` (confirmed against the installed `resend` package —
    genuinely async, not sync-wrapped-in-a-thread).
    """

    def __init__(self) -> None:
        resend.api_key = settings.RESEND_API_KEY

    async def send(self, *, to: str, subject: str, html_body: str) -> None:
        params: resend.Emails.SendParams = {
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
            "to": [to],
            "subject": subject,
            "html": html_body,
        }
        try:
            await resend.Emails.send_async(params)
        except Exception:
            # Logged with exc_info so Sentry/structured logs capture the
            # real Resend error. A failed sending should not surface the raw
            # provider exception to the HTTP caller — see otp_service,
            # which treats "could I send" as an internal concern, not
            # something that changes the response the client sees. (Same
            # enumeration-safety reasoning as the request endpoint itself.)
            logger.error("email_send_failed", to=to, subject=subject, exc_info=True)
            raise
        logger.info("email_sent", to=to, subject=subject)
