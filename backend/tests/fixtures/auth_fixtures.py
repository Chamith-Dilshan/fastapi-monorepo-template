import pytest_asyncio
from httpx import AsyncClient

from tests.utils.helpers import create_authenticated_user


@pytest_asyncio.fixture
async def authenticated_user(client: AsyncClient):
    """Returns (user_dict, auth_headers) for a freshly registered user."""
    user, headers = await create_authenticated_user(client)
    return user, headers


@pytest_asyncio.fixture
async def auth_headers(authenticated_user):
    """Returns only the Authorization headers dict."""
    _, headers = authenticated_user
    return headers


@pytest_asyncio.fixture
async def user(authenticated_user):
    """Returns only the user dict."""
    user_dict, _ = authenticated_user
    return user_dict
