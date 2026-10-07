"""One mechanism, three purposes (OTPPurpose.EMAIL_VERIFICATION /
PASSWORD_RESET / TWO_FACTOR) — see app/models/otp_code.py. Every caller
goes through `generate_and_send` and `verify`; nothing outside this module
touches OTPRepository directly, so "how a code is generated, hashed, and
checked" stays in exactly one place regardless of how many purposes use it.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidOTPException
from app.core.logging import get_logger
from app.core.security import get_password_hash, verify_password
from app.models.otp_code import OTPCode, OTPPurpose
from app.models.user import User
from app.repositories.otp_repository import OTPRepository
from app.services.email_service import EmailService

logger = get_logger("app.otp")


def _generate_code(length: int) -> str:
    # secrets, not random — this is a credential, not a test fixture.
    return "".join(secrets.choice("0123456789") for _ in range(length))


class OTPService:
    def __init__(self, db: AsyncSession, email_service: EmailService | None = None) -> None:
        self.db = db
        self.repository = OTPRepository(db)
        self.email_service = email_service or EmailService()

    async def generate_and_send(self, user: User, purpose: OTPPurpose) -> None:
        # A new request invalidates whatever code was issued before for
        # the same purpose — only ever one valid code per user/purpose.
        await self.repository.invalidate_active(user.id, purpose)

        code = _generate_code(settings.OTP_LENGTH)
        otp = OTPCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=get_password_hash(code),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        )
        await self.repository.create(otp)

        try:
            await self.email_service.send_otp_code(to=user.email, purpose=purpose, code=code)
        except Exception:
            # The code is already persisted and will work if entered, even
            # if delivery failed — don't raise here, or a flaky mail
            # provider would turn into a 500 on an otherwise-successful
            # request. The failure is still logged (by ResendEmailSender
            # itself) and visible in Sentry/traces.
            logger.warning("otp_email_send_failed", user_id=str(user.id), purpose=purpose.value)

    async def verify(self, user: User, purpose: OTPPurpose, code: str) -> None:
        otp = await self.repository.get_active(user.id, purpose)

        if otp is None:
            raise InvalidOTPException()

        if otp.expires_at < datetime.now(UTC):
            raise InvalidOTPException()

        if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise InvalidOTPException()

        if not verify_password(code, otp.code_hash):
            await self.repository.increment_attempts(otp)
            raise InvalidOTPException()

        await self.repository.mark_consumed(otp)
