import pytest_asyncio
from httpx import AsyncClient

from tests.utils.helpers import create_authenticated_user


@pytest_asyncio.fixture
async def second_user(client: AsyncClient):
    """A second independent authenticated user for authorization tests."""
    user, headers = await create_authenticated_user(client)
    return user, headers
