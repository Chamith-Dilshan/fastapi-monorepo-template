from app.core.email.base import EmailSender
from app.core.logging import get_logger

logger = get_logger("app.email.console")


class ConsoleEmailSender(EmailSender):
    """Default sender. Logs the email instead of sending it — used in
    local dev and, implicitly, in tests (nothing in the test suite sets
    EMAIL_PROVIDER=resend). The full HTML body is logged at DEBUG, so an
    OTP code is actually readable during local testing without a real
    inbox; everything else is INFO.
    """

    async def send(self, *, to: str, subject: str, html_body: str) -> None:
        logger.info("email_send_console", to=to, subject=subject)
        logger.debug("email_body_console", to=to, html_body=html_body)
