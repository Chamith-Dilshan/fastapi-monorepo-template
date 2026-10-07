"""The interface every email sender implements, and the factory that picks
one based on `settings.EMAIL_PROVIDER`.

Callers (otp_service, etc.) depend on `EmailSender`, never on
`ResendEmailSender` or `ConsoleEmailSender` directly — that's what lets
tests swap in `ConsoleEmailSender` (or a spy) without touching anything
that calls `send()`.
"""

from abc import ABC, abstractmethod


class EmailSender(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, html_body: str) -> None: ...


def get_email_sender() -> EmailSender:
    from app.core.config import settings

    if settings.EMAIL_PROVIDER == "resend":
        from app.core.email.resend_sender import ResendEmailSender

        return ResendEmailSender()

    from app.core.email.console_sender import ConsoleEmailSender

    return ConsoleEmailSender()
