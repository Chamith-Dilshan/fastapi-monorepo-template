from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.models.refresh_token import RefreshToken


class TokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, token: RefreshToken) -> RefreshToken:
        try:
            self.db.add(token)
            await self.db.flush()
            return token
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        try:
            result = await self.db.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def revoke(self, token: RefreshToken) -> None:
        try:
            token.revoked_at = datetime.now(UTC)
            await self.db.flush()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def revoke_family(self, family_id: UUID) -> None:
        try:
            await self.db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == family_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            await self.db.flush()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        try:
            await self.db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            await self.db.flush()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc
