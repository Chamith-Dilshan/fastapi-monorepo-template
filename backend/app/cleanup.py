"""Housekeeping, run on a schedule:

    python -m app.cleanup

Nothing here is needed for correctness — expired tokens and codes are
rejected when used whether or not their rows still exist. It only stops
tables growing forever. Safe to run as often as you like and to run twice.

What it removes, and what it deliberately keeps:

- Refresh tokens, a day after they *expire*. Revoked-but-unexpired tokens
  stay: reuse detection works by finding a revoked token being replayed.
- One-time codes (email verification, password reset, 2FA, OAuth exchange),
  a day after they expire — used or not.
- Accounts that never verified their email, after UNVERIFIED_USER_TTL_DAYS.
  They cannot log in, so there is nothing of theirs to lose.
- Audit logs only if AUDIT_LOG_RETENTION_DAYS is set. Otherwise, never.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Delete, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

import app.models.models  # noqa: F401 (registers every model with the ORM)
from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging, get_logger
from app.models.audit_log import AuditLog
from app.models.otp_code import OTPCode
from app.models.refresh_token import RefreshToken
from app.models.user import User

logger = get_logger("app.cleanup")

_GRACE = timedelta(days=1)


async def _delete(session: AsyncSession, statement: Delete) -> int:
    """Runs a DELETE and returns how many rows it removed. The type stubs
    declare `execute()` as returning a plain `Result`; a DELETE is in fact a
    `CursorResult`, which is where `rowcount` lives."""
    result = cast(CursorResult[Any], await session.execute(statement))
    return result.rowcount or 0


async def run_cleanup(session: AsyncSession) -> dict[str, int]:
    """Does the work inside the caller's transaction and returns row counts.
    The caller commits (see main), which keeps this testable."""
    now = datetime.now(UTC)
    removed: dict[str, int] = {}

    removed["refresh_tokens"] = await _delete(
        session, delete(RefreshToken).where(RefreshToken.expires_at < now - _GRACE)
    )

    removed["otp_codes"] = await _delete(
        session, delete(OTPCode).where(OTPCode.expires_at < now - _GRACE)
    )

    removed["unverified_users"] = await _delete(
        session,
        delete(User).where(
            User.is_verified.is_(False),
            User.created_at < now - timedelta(days=settings.UNVERIFIED_USER_TTL_DAYS),
        ),
    )
    if removed["unverified_users"]:
        # Deleting accounts in bulk is worth a trace of its own.
        await record_audit_event(
            session,
            action="user.unverified_purged",
            resource_type="user",
            metadata={
                "count": removed["unverified_users"],
                "older_than_days": settings.UNVERIFIED_USER_TTL_DAYS,
            },
        )

    if settings.AUDIT_LOG_RETENTION_DAYS is not None:
        removed["audit_logs"] = await _delete(
            session,
            delete(AuditLog).where(
                AuditLog.created_at
                < now - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
            ),
        )

    return removed


async def _main() -> None:
    # A script, not a request: it owns its transaction, like initial_data.
    async with AsyncSessionFactory() as session:
        removed = await run_cleanup(session)
        await session.commit()
    logger.info("cleanup_finished", **removed)


def main() -> None:
    configure_logging()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
