from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from faker import Faker
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.base import Base
from app.core.config import settings
from app.core.database import get_db
from app.main import app

# Import models so the test schema (built via create_all below, not
# Alembic — a deliberate, separate shortcut for test isolation speed)
# includes every table.
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.oauth_account import OAuthAccount  # noqa: F401
from app.models.otp_code import OTPCode  # noqa: F401
from app.models.user import User  # noqa: F401


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator:
    engine = create_async_engine(
        settings.test_database_url,
        echo=False,
        pool_pre_ping=True,
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def reset_database(db_engine) -> AsyncGenerator[None]:
    """Start every test with a brand-new schema and no shared data."""
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def db_session(reset_database, db_engine) -> AsyncGenerator[AsyncSession]:  # noqa: ARG001
    # `reset_database` is a pytest fixture dependency, not a value this
    # fixture uses — the parameter *name* must match the fixture name
    # exactly for pytest's injection to find it, so it can't be prefixed
    # with `_` the way an ordinary unused argument would be.
    session_factory = async_sessionmaker(
        bind=db_engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def faker() -> Faker:
    return Faker()
