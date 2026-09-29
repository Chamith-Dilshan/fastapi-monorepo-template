import pytest
from httpx import AsyncClient

from tests.factories.post_factory import PostFactory
from tests.utils.constants import LIKES_URL, POSTS_URL
from tests.utils.helpers import create_authenticated_user


@pytest.fixture
async def created_post(client: AsyncClient, auth_headers: dict) -> dict:
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_like_post_first_call(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.post(
        f"{LIKES_URL}/{created_post['id']}/like",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["liked"] is True
    assert str(data["post_id"]) == created_post["id"]


async def test_unlike_post_second_call(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    response = await client.post(
        f"{LIKES_URL}/{created_post['id']}/like",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["liked"] is False


async def test_like_again_third_call(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    response = await client.post(
        f"{LIKES_URL}/{created_post['id']}/like",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["liked"] is True


async def test_like_increments_like_count(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    before = (
        await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)
    ).json()["like_count"]

    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)

    after = (
        await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)
    ).json()["like_count"]

    assert after == before + 1


async def test_unlike_decrements_like_count(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    liked_count = (
        await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)
    ).json()["like_count"]

    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    unliked_count = (
        await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)
    ).json()["like_count"]

    assert unliked_count == liked_count - 1


async def test_is_liked_reflects_state(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    before = (
        await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)
    ).json()["is_liked"]
    assert before is False

    await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    after = (
        await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)
    ).json()["is_liked"]
    assert after is True


async def test_multiple_users_can_like_same_post(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    _, other_headers = await create_authenticated_user(client)

    r1 = await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=auth_headers)
    r2 = await client.post(f"{LIKES_URL}/{created_post['id']}/like", headers=other_headers)

    assert r1.json()["liked"] is True
    assert r2.json()["liked"] is True


@pytest.mark.parametrize(
    ("post_id", "expected_status"),
    [
        ("00000000-0000-0000-0000-000000000000", 404),
        ("not-a-uuid", 422),
    ],
)
async def test_like_post_invalid_or_missing_targets(
    client: AsyncClient,
    auth_headers: dict,
    post_id: str,
    expected_status: int,
):
    response = await client.post(f"{LIKES_URL}/{post_id}/like", headers=auth_headers)

    assert response.status_code == expected_status


async def test_like_post_unauthorized(client: AsyncClient, created_post: dict):
    response = await client.post(f"{LIKES_URL}/{created_post['id']}/like")

    assert response.status_code == 401


async def test_like_response_contains_post_id(
    client: AsyncClient,
    auth_headers: dict,
    created_post: dict,
):
    response = await client.post(
        f"{LIKES_URL}/{created_post['id']}/like",
        headers=auth_headers,
    )

    data = response.json()
    assert "liked" in data
    assert "post_id" in data
    assert isinstance(data["liked"], bool)
