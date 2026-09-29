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
    async with AsyncSessionFactory() as session:
        yield session
