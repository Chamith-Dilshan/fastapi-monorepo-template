from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.models.otp_code import OTPCode, OTPPurpose


class OTPRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, otp: OTPCode) -> OTPCode:
        try:
            self.db.add(otp)
            await self.db.flush()
            return otp
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def get_active(self, user_id: UUID, purpose: OTPPurpose) -> OTPCode | None:
        """The most recent not-yet-consumed row for this user/purpose,
        regardless of whether it's expired — the service layer decides
        expired-vs-valid, this just finds the candidate to check.
        """
        try:
            result = await self.db.execute(
                select(OTPCode)
                .where(
                    OTPCode.user_id == user_id,
                    OTPCode.purpose == purpose,
                    OTPCode.consumed_at.is_(None),
                )
                .order_by(OTPCode.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def invalidate_active(self, user_id: UUID, purpose: OTPPurpose) -> None:
        """Marks every not-yet-consumed row for this user/purpose as
        consumed (without real verification), so requesting a new code
        makes the previous one stop working instead of leaving two valid
        codes outstanding at once.
        """
        try:
            await self.db.execute(
                update(OTPCode)
                .where(
                    OTPCode.user_id == user_id,
                    OTPCode.purpose == purpose,
                    OTPCode.consumed_at.is_(None),
                )
                .values(consumed_at=datetime.now(UTC))
            )
            await self.db.flush()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def increment_attempts(self, otp: OTPCode) -> None:
        try:
            otp.attempts += 1
            await self.db.flush()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def mark_consumed(self, otp: OTPCode) -> None:
        try:
            otp.consumed_at = datetime.now(UTC)
            await self.db.flush()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc
