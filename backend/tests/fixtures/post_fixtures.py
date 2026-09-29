import pytest_asyncio
from httpx import AsyncClient

from tests.factories.post_factory import PostFactory
from tests.utils.constants import POSTS_URL


@pytest_asyncio.fixture
async def post(client: AsyncClient, auth_headers: dict):
    """Creates a single post owned by the primary-authenticated user."""
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()
