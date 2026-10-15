"""Access + refresh token issuing, rotation, and revocation.

Access tokens are short-lived JWTs (app.core.security.create_access_token).
Refresh tokens are opaque random strings stored only as a SHA-256 hash (see
app/models/refresh_token.py), rotated on every use, and grouped into
"families" so replaying a stolen token can be detected and punished.

Known trade-off, on purpose: two browser tabs refreshing with the *same*
token at the same instant look exactly like a replay and will log that
session out. The frontend avoids it by funneling every refresh through one
in-flight request (single-flight) instead of this service adding a grace
window that would also soften real theft detection.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import RefreshTokenReuseException, UnauthorizedException
from app.core.security import create_access_token
from app.dtos.token_dto import Token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class TokenService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = TokenRepository(db)
        self.user_repository = UserRepository(db)

    async def issue_pair(self, user: User, *, family_id: UUID | None = None) -> Token:
        raw_refresh = secrets.token_urlsafe(48)
        await self.repository.create(
            RefreshToken(
                user_id=user.id,
                family_id=family_id or uuid4(),
                token_hash=_hash(raw_refresh),
                expires_at=datetime.now(UTC)
                + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        return Token(
            access_token=create_access_token(data={"sub": str(user.id)}),
            refresh_token=raw_refresh,
            token_type="bearer",
        )

    async def refresh(self, raw_refresh_token: str) -> Token:
        record = await self.repository.get_by_hash(_hash(raw_refresh_token))

        if record is None:
            raise UnauthorizedException(message="Invalid refresh token")

        if record.revoked_at is not None:
            # Already rotated away (or logged out) and now presented again:
            # treat the whole family as compromised. The exception below
            # opts in to being committed so this revocation survives the 401.
            await self.repository.revoke_family(record.family_id)
            raise RefreshTokenReuseException()

        if record.expires_at < datetime.now(UTC):
            raise UnauthorizedException(message="Invalid refresh token")

        user = await self.user_repository.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedException(message="Invalid refresh token")

        await self.repository.revoke(record)
        return await self.issue_pair(user, family_id=record.family_id)

    async def revoke(self, raw_refresh_token: str) -> None:
        """Logout. Revokes the whole family, so every token descended from
        this login stops working. Unknown tokens are ignored — logging out
        twice, or with garbage, is not an error worth reporting.
        """
        record = await self.repository.get_by_hash(_hash(raw_refresh_token))
        if record is not None:
            await self.repository.revoke_family(record.family_id)

    async def revoke_all(self, user_id: UUID) -> None:
        await self.repository.revoke_all_for_user(user_id)
