"""One mechanism, several purposes (OTPPurpose.EMAIL_VERIFICATION /
PASSWORD_RESET / TWO_FACTOR / OAUTH_LOGIN) — see app/models/otp_code.py. Every caller
goes through `generate_and_send` and `verify`; nothing outside this module
touches OTPRepository directly, so "how a code is generated, hashed, and
checked" stays in exactly one place regardless of how many purposes use it.
"""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidOTPException
from app.core.logging import get_logger
from app.core.security import get_password_hash, verify_password
from app.models.otp_code import OTPCode, OTPPurpose
from app.models.user import User
from app.repositories.otp_repository import OTPRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService

logger = get_logger("app.otp")


def _generate_code(length: int) -> str:
    # secrets, not random — this is a credential, not a test fixture.
    return "".join(secrets.choice("0123456789") for _ in range(length))


class OTPService:
    def __init__(
        self, db: AsyncSession, email_service: EmailService | None = None
    ) -> None:
        self.db = db
        self.repository = OTPRepository(db)
        self.email_service = email_service or EmailService()

    async def generate_and_send(self, user: User, purpose: OTPPurpose) -> bool:
        """Issues a fresh code and emails it. Returns False — and does
        nothing — if a code for this user/purpose was issued within the
        resend cooldown and is still usable, so repeated requests can't be
        used to spam an inbox. Callers must not reveal the difference.
        """
        now = datetime.now(UTC)

        outstanding = await self.repository.get_active(user.id, purpose)
        if (
            outstanding is not None
            and outstanding.expires_at > now
            and outstanding.created_at
            > now - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
        ):
            logger.info(
                "otp_resend_suppressed", user_id=str(user.id), purpose=purpose.value
            )
            return False

        # A new request invalidates whatever code was issued before for
        # the same purpose — only ever one valid code per user/purpose.
        await self.repository.invalidate_active(user.id, purpose)

        code = _generate_code(settings.OTP_LENGTH)
        otp = OTPCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=get_password_hash(code),
            expires_at=now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
            # Set here, not left to the column's server default: Postgres
            # `now()` is the *transaction's* start time, which would make
            # the cooldown above compare against the wrong clock.
            created_at=now,
        )
        await self.repository.create(otp)

        try:
            await self.email_service.send_otp_code(
                to=user.email, purpose=purpose, code=code
            )
        except Exception:
            # The code is already persisted and will work if entered, even
            # if delivery failed — don't raise here, or a flaky mail
            # provider would turn into a 500 on an otherwise-successful
            # request. The failure is still logged (by the sender itself)
            # and visible in Sentry/traces.
            logger.warning(
                "otp_email_send_failed", user_id=str(user.id), purpose=purpose.value
            )
        return True

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

    # --- OAuth exchange code ---------------------------------------------
    # Not an emailed code. After Google sign-in, the browser is redirected to
    # the frontend, and anything in that URL ends up in history and logs —
    # so the URL carries this single-use, 60-second code instead of tokens,
    # and the frontend swaps it for real tokens with one POST. The same table,
    # same hashing, same single-use/attempt rules as every other OTP.

    async def issue_exchange_code(self, user: User) -> str:
        await self.repository.invalidate_active(user.id, OTPPurpose.OAUTH_LOGIN)
        secret = secrets.token_urlsafe(32)
        await self.repository.create(
            OTPCode(
                user_id=user.id,
                purpose=OTPPurpose.OAUTH_LOGIN,
                code_hash=get_password_hash(secret),
                expires_at=datetime.now(UTC) + timedelta(seconds=60),
            )
        )
        # The user id travels in the code, so redeeming it needs no other
        # input; it is an identifier, not a credential.
        return f"{user.id}.{secret}"

    async def redeem_exchange_code(self, code: str) -> User:
        try:
            user_id_part, secret = code.split(".", 1)
            user_id = UUID(user_id_part)
        except ValueError:
            raise InvalidOTPException() from None

        user = await UserRepository(self.db).get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidOTPException()

        await self.verify(user, OTPPurpose.OAUTH_LOGIN, secret)
        return user
