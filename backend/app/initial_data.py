"""Creates the first admin account if one is configured and missing.

    python -m app.initial_data

Run by scripts/prestart.sh on every deployment, so it has to be safe to run
repeatedly: it only ever *creates*. If the email already exists, it does
nothing — it will not reset that account's password, and it will not quietly
promote an existing non-admin to admin (an env var must not be a back door
into privilege escalation).
"""

import asyncio

import app.models.models  # noqa: F401 (registers every model with the ORM)
from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging, get_logger
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository

logger = get_logger("app.initial_data")


async def create_first_admin() -> None:
    email = settings.FIRST_ADMIN_EMAIL
    password = settings.FIRST_ADMIN_PASSWORD

    if not email or not password:
        logger.info("initial_admin_skipped", reason="FIRST_ADMIN_* not configured")
        return

    # A script, not a request: it owns its own transaction, so it commits
    # itself rather than going through get_db.
    async with AsyncSessionFactory() as session:
        repository = UserRepository(session)
        existing = await repository.get_by_email(email)

        if existing is not None:
            if existing.role != UserRole.ADMIN:
                logger.warning(
                    "initial_admin_exists_but_not_admin",
                    email=email,
                    hint="Promote the account through the admin API; "
                    "this script never changes existing accounts.",
                )
            else:
                logger.info("initial_admin_already_exists", email=email)
            return

        await repository.create(
            User(
                email=email,
                hashed_password=get_password_hash(password),
                first_name="Admin",
                last_name="User",
                role=UserRole.ADMIN,
                # Configured by whoever runs the deployment — no inbox to
                # prove, and an unverified admin would be a pointless trap.
                is_verified=True,
            )
        )
        await session.commit()
        logger.info("initial_admin_created", email=email)


def main() -> None:
    configure_logging()
    asyncio.run(create_first_admin())


if __name__ == "__main__":
    main()
