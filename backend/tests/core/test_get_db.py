"""The real `get_db` (not the fixture override every other test uses): what
commits, what rolls back, and the one deliberate exception."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.core.database as database
from app.core.exceptions import (
    NotFoundException,
    RefreshTokenReuseException,
)
from app.core.security import get_password_hash
from app.models.user import User


@pytest_asyncio.fixture
async def factory(reset_database, db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionFactory", session_factory)
    return session_factory


async def _exists(factory, email: str) -> bool:
    async with factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none() is not None


def _user(email: str) -> User:
    return User(
        email=email,
        hashed_password=get_password_hash("x"),
        first_name="A",
        last_name="B",
    )


async def _write_then(email: str, exception: Exception | None):
    gen = database.get_db()
    session: AsyncSession = await gen.__anext__()
    session.add(_user(email))
    await session.flush()
    if exception is None:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    else:
        with pytest.raises(type(exception)):
            await gen.athrow(exception)


@pytest.mark.asyncio
async def test_clean_return_commits(factory):
    await _write_then("ok@example.com", None)
    assert await _exists(factory, "ok@example.com")


@pytest.mark.asyncio
async def test_an_exception_rolls_everything_back(factory):
    await _write_then("gone@example.com", ValueError("boom"))
    assert not await _exists(factory, "gone@example.com")


@pytest.mark.asyncio
async def test_an_ordinary_app_exception_also_rolls_back(factory):
    await _write_then("gone2@example.com", NotFoundException(message="nope"))
    assert not await _exists(factory, "gone2@example.com")


@pytest.mark.asyncio
async def test_token_reuse_exception_commits_despite_failing(factory):
    # The one opt-in: revoking a compromised token family must survive the 401.
    await _write_then("kept@example.com", RefreshTokenReuseException())
    assert await _exists(factory, "kept@example.com")
