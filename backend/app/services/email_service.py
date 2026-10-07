from app.core.config import settings
from app.core.email.base import EmailSender, get_email_sender
from app.emails.renderer import render_template
from app.models.otp_code import OTPPurpose

_OTP_COPY: dict[OTPPurpose, tuple[str, str]] = {
    # purpose -> (subject, intro_text)
    OTPPurpose.EMAIL_VERIFICATION: (
        "Verify your email",
        "Enter this code to verify your email address.",
    ),
    OTPPurpose.PASSWORD_RESET: (
        "Reset your password",
        "Enter this code to reset your password.",
    ),
    OTPPurpose.TWO_FACTOR: (
        "Your sign-in code",
        "Enter this code to finish signing in.",
    ),
}


class EmailService:
    """Thin, purpose-specific wrapper around `EmailSender` + the Jinja2
    templates. `otp_service.py` and `oauth_service.py` depend on this, not
    on `EmailSender` directly — this is where "which template, which
    subject line" lives, kept out of the services that only care about
    OTP/account logic.
    """

    def __init__(self, sender: EmailSender | None = None) -> None:
        self._sender = sender or get_email_sender()

    async def send_otp_code(self, *, to: str, purpose: OTPPurpose, code: str) -> None:
        subject, intro_text = _OTP_COPY[purpose]
        html_body = render_template(
            "otp_code.html",
            app_name=settings.APP_NAME,
            intro_text=intro_text,
            code=code,
            expire_minutes=settings.OTP_EXPIRE_MINUTES,
        )
        await self._sender.send(to=to, subject=subject, html_body=html_body)

    async def send_welcome_email(self, *, to: str, first_name: str) -> None:
        html_body = render_template(
            "welcome.html",
            app_name=settings.APP_NAME,
            first_name=first_name,
        )
        await self._sender.send(to=to, subject=f"Welcome to {settings.APP_NAME}", html_body=html_body)
