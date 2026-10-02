from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class OAuthProvider(StrEnum):
    """Google only for now. Adding GitHub/Microsoft/Apple later is a new
    value here plus a new provider adapter in `services/oauth_service.py` —
    no schema change, since this is stored as VARCHAR (see OAuthAccount
    below), the same reasoning as `UserRole`.
    """

    GOOGLE = "google"


class OAuthAccount(Base):
    """Links a User to one external identity. A user can have more than one
    (e.g., Google + GitHub once that exists), so this is a child table, not
    columns on User.
    """

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        # One external identity maps to exactly one user.
        UniqueConstraint(
            "provider", "provider_account_id", name="uq_oauth_provider_account"
        ),
        # A user can't link the same provider twice.
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[OAuthProvider] = mapped_column(
        SAEnum(OAuthProvider, native_enum=False, length=20, validate_strings=True),
        nullable=False,
    )

    # The provider's own stable subject id (Google's `sub` claim) — never
    # the user's email, which can change on the provider's side.
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="oauth_accounts")
