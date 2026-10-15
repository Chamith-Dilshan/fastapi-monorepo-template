from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class RefreshToken(Base):
    """One row per refresh token ever issued. The raw token is never
    stored — only its SHA-256 (the token is 256 bits of randomness, so a
    fast hash is fine here; Argon2 is for low-entropy secrets like
    passwords and 6-digit codes).

    `family_id` ties together every token descended from one login. Using a
    refresh token revokes it and issues a child in the same family
    (rotation). Presenting an already-revoked token means someone is
    replaying a stolen copy, so the whole family is revoked at once — see
    TokenService.refresh.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    family_id: Mapped[UUID] = mapped_column(nullable=False, index=True)

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
