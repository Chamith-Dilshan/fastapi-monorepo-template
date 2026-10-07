# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker
#
# from app.core.config import Settings
#
# settings = Settings()
#
# engine = create_engine(settings.database_url)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
#
# Base = declarative_base()
#
#
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

"""
Alembic And SQLAlchemy URL Escaping
====================

Database passwords may contain special characters such as:

    @  #  %  $  !  &

When building a SQLAlchemy connection URL, these characters must first
be URL-encoded.

Example:

    Password:
        my#password

    URL-encoded:
        my%23password

SQLAlchemy accepts the encoded URL directly:

    postgresql+asyncpg://user:my%23password@localhost/db

However, Alembic's Config.set_main_option() uses Python's ConfigParser
internally. ConfigParser treats '%' as a special interpolation character.

This means a URL containing:

    %23

will raise:

    ValueError: invalid interpolation syntax

unless the percent signs are escaped.

Before passing the URL to Alembic, replace:

    %  ->  %%

Example:

    DATABASE_URL = (
        settings.database_url
        .replace("%", "%%")
    )

This converts:

    postgresql+asyncpg://user:my%23password@localhost/db

into:

    postgresql+asyncpg://user:my%%23password@localhost/db

which Alembic can safely process.

References:
- SQLAlchemy URL encoding is required for special characters in
  usernames/passwords.
- Alembic Config.set_main_option() uses ConfigParser interpolation,
  which requires literal '%' characters to be escaped as '%%'.
"""

engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """One transaction per request. This is the *only* place that commits
    — every repository (UserRepository, OTPRepository, OAuthRepository)
    only ever flushes, deliberately. That means:

    - A route calling two different repositories (e.g., verifying an OTP
      via OTPRepository, then updating the user via UserRepository) gets
      atomicity for free, without the route needing to know transactions
      exist — the two flushes land together in one commit when the
      request finishes cleanly.
    - If anything raises partway through a request — including one of our
      own AppException subclasses — everything that happened earlier in
      that same request rolls back too, instead of leaving whatever
      already-committed writes happened before the failure.

    No route or service should call `db.commit()` directly; if one needs
    to guarantee a prior write is durable before doing something external
    (sending an email, calling a third-party API), that's a sign the work
    should be split across two requests/transactions, not a reason to
    commit early here.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
