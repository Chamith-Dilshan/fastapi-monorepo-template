from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class OTPPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    TWO_FACTOR = "two_factor"


class OTPCode(Base):
    """One mechanism, three purposes. `otp_service.py` always
    verifies purpose + expiry + attempt count together — never just "does
    this code match any row for this user".

    Rows are not deleted after use; `consumed_at` marks them spent so a
    replayed code is rejected, and the history is useful for abuse
    detection later. A cleanup job can prune old expired/consumed rows once
    that's worth doing — not needed for the template.
    """

    __tablename__ = "otp_codes"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    purpose: Mapped[OTPPurpose] = mapped_column(
        SAEnum(OTPPurpose, native_enum=False, length=30, validate_strings=True),
        nullable=False,
        index=True,
    )

    # Hash of the code, never the code itself — the same principle as passwords.
    # A 6-digit numeric code has too little entropy to bother salting per
    # row; hash with the same Argon2 hasher used for passwords
    # (`core/security.py`), so there's one hashing primitive in the codebase.
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Failed to verify attempts against this specific row. otp_service should
    # stop accepting attempts past a small limit (e.g., 5) even before
    # expiry, to blunt brute-forcing a 6-digit code.
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="otp_codes")
