from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.models.oauth_account import OAuthAccount
    from app.models.otp_code import OTPCode


class UserRole(StrEnum):
    """Deliberately stored as a plain VARCHAR (see the column below), not a
    Postgres native ENUM type. Native enums need an `ALTER TYPE` migration
    to add/rename a value; a VARCHAR + Python-side Enum means changing the
    role set later is a code change plus a data migration if needed, not a
    schema migration. Matches "we can change these roles later".
    """

    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    GUEST = "guest"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # Nullable: a user who only ever signs in via Google (see OAuthAccount)
    # has no password at all — don't fake one.
    hashed_password: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, length=20, validate_strings=True),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )

    # Account disabled by an admin (or self-deleted, soft-disable style).
    # Checked in the auth dependency alongside token validity.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    # Flipped true once an email_verification OTP is confirmed, or
    # immediately for an OAuth signup (the provider already verified it).
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    # When true, UserService.authenticate_user succeeding is not enough to
    # issue tokens — the login endpoint instead sends a two_factor OTP and
    # the client must call /auth/2fa/verify. See services/otp_service.py.
    is_2fa_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    otp_codes: Mapped[list[OTPCode]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
