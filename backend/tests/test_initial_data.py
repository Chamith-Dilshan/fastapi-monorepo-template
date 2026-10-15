import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.initial_data as initial_data
from app.core.config import settings
from app.models.user import User, UserRole


@pytest.fixture
def bootstrap(reset_database, db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(initial_data, "AsyncSessionFactory", factory)

    async def run(email="root@example.com", password="a-real-password-1"):
        monkeypatch.setattr(settings, "FIRST_ADMIN_EMAIL", email)
        monkeypatch.setattr(settings, "FIRST_ADMIN_PASSWORD", password)
        await initial_data.create_first_admin()

    async def users():
        async with factory() as session:
            return (await session.execute(select(User))).scalars().all()

    return run, users, factory


@pytest.mark.asyncio
async def test_creates_a_verified_admin(bootstrap):
    run, users, _ = bootstrap
    await run()
    [admin] = await users()
    assert admin.email == "root@example.com"
    assert admin.role == UserRole.ADMIN
    assert admin.is_verified is True
    assert admin.hashed_password != "a-real-password-1"


@pytest.mark.asyncio
async def test_is_safe_to_run_on_every_deploy(bootstrap):
    run, users, _ = bootstrap
    await run()
    [first] = await users()
    await run(password="a-different-password-2")  # must not reset the password
    [second] = await users()
    assert first.id == second.id
    assert first.hashed_password == second.hashed_password


@pytest.mark.asyncio
async def test_never_promotes_an_existing_non_admin(bootstrap):
    run, users, factory = bootstrap
    async with factory() as session:
        session.add(
            User(
                email="root@example.com",
                hashed_password="x",
                first_name="A",
                last_name="B",
            )
        )
        await session.commit()

    await run()
    [user] = await users()
    assert user.role == UserRole.USER


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password"), [(None, "x"), ("a@example.com", None), (None, None)]
)
async def test_does_nothing_unless_fully_configured(
    bootstrap, monkeypatch, email, password
):
    _, users, _ = bootstrap
    monkeypatch.setattr(settings, "FIRST_ADMIN_EMAIL", email)
    monkeypatch.setattr(settings, "FIRST_ADMIN_PASSWORD", password)
    await initial_data.create_first_admin()
    assert await users() == []
