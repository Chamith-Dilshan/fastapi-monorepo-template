from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from faker import Faker
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.base import Base
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_password_hash
from app.main import app

# Registers every model, so the test schema (built via create_all below,
# not Alembic — a deliberate shortcut for test isolation speed) includes
# every table without this file needing to list them.
from app.models import models as _all_models  # noqa: F401
from app.models.user import User, UserRole


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
async def db_session(reset_database, db_engine) -> AsyncGenerator[AsyncSession]:
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


DEFAULT_PASSWORD = "StrongP@ssw0rd!"


@pytest_asyncio.fixture
async def make_user(db_session: AsyncSession, faker: Faker):
    """Creates a user straight in the database (bypassing the API), so a
    test can have an admin/manager/disabled account without going through
    registration, which only ever produces role=user.
    """

    async def _make(
        *,
        role: UserRole = UserRole.USER,
        is_active: bool = True,
        is_verified: bool = True,
        password: str | None = DEFAULT_PASSWORD,
        email: str | None = None,
    ) -> User:
        user = User(
            email=email or faker.unique.email(),
            hashed_password=get_password_hash(password) if password else None,
            first_name=faker.first_name(),
            last_name=faker.last_name(),
            role=role,
            is_active=is_active,
            is_verified=is_verified,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _make


@pytest_asyncio.fixture
async def login(client: AsyncClient):
    """Logs a user in through the real /auth/login and returns the JSON
    body (access_token, refresh_token, ...)."""

    async def _login(user: User, password: str = DEFAULT_PASSWORD) -> dict:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": user.email, "password": password},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _login


@pytest_asyncio.fixture
async def auth_headers(login):
    async def _headers(user: User, password: str = DEFAULT_PASSWORD) -> dict:
        tokens = await login(user, password)
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    return _headers


@pytest.fixture(autouse=True)
def _no_resend_cooldown(monkeypatch):
    """The resend cooldown would make back-to-back requests in a test
    silently do nothing. Off by default; tests of the cooldown itself turn
    it back on."""
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)


@pytest.fixture
def sent_codes(monkeypatch) -> list[dict]:
    """Stands in for email delivery and records what would have been sent —
    the only way a test can learn a one-time code, since they are never
    stored in the clear."""
    sent: list[dict] = []

    async def fake_send(self, *, to, purpose, code):
        sent.append({"to": to, "purpose": purpose, "code": code})

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send
    )
    return sent
