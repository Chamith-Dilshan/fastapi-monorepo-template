from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.models.oauth_account import OAuthAccount, OAuthProvider


class OAuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_provider_account(
        self, provider: OAuthProvider, provider_account_id: str
    ) -> OAuthAccount | None:
        try:
            result = await self.db.execute(
                select(OAuthAccount).where(
                    OAuthAccount.provider == provider,
                    OAuthAccount.provider_account_id == provider_account_id,
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc

    async def create(
        self, user_id: UUID, provider: OAuthProvider, provider_account_id: str
    ) -> OAuthAccount:
        try:
            account = OAuthAccount(
                user_id=user_id,
                provider=provider,
                provider_account_id=provider_account_id,
            )
            self.db.add(account)
            await self.db.flush()
            return account
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc
