import pytest
from httpx import AsyncClient

from tests.factories.post_factory import PostFactory
from tests.utils.constants import POSTS_URL, PUBLIC_POSTS_URL
from tests.utils.helpers import create_authenticated_user


@pytest.fixture
async def created_post(client: AsyncClient, auth_headers: dict) -> dict:
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def three_posts(client: AsyncClient, auth_headers: dict) -> list[dict]:
    posts = []
    for _ in range(3):
        payload = PostFactory.build()
        response = await client.post(POSTS_URL, json=payload, headers=auth_headers)
        assert response.status_code == 201, response.text
        posts.append(response.json())
    return posts


@pytest.mark.parametrize(
    ("payload_override", "expected_status"),
    [
        ({"title": ""}, 422),
        ({"content": ""}, 422),
        ({"title": None}, 422),
        ({"content": None}, 422),
    ],
)
async def test_create_post_validation_errors(
    client: AsyncClient,
    auth_headers: dict,
    payload_override: dict,
    expected_status: int,
):
    payload = PostFactory.build(**payload_override)
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == expected_status


async def test_create_post_success(client: AsyncClient, auth_headers: dict):
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["content"] == payload["content"]
    assert "id" in data
    assert "author" in data


async def test_create_post_unauthorized(client: AsyncClient):
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload)

    assert response.status_code == 401


async def test_create_post_response_has_author(
    client: AsyncClient,
    auth_headers: dict,
    user: dict,
):
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == 201
    assert response.json()["author"]["id"] == user["id"]


async def test_create_post_like_count_zero(client: AsyncClient, auth_headers: dict):
    payload = PostFactory.build()
    response = await client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == 201
    assert response.json().get("like_count", 0) == 0


async def test_my_posts_success(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(POSTS_URL, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(post["id"] == created_post["id"] for post in data["items"])


async def test_my_posts_empty_for_new_user(client: AsyncClient):
    _, headers = await create_authenticated_user(client)
    response = await client.get(POSTS_URL, headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_my_posts_search(client: AsyncClient, auth_headers: dict, created_post: dict):
    title_fragment = created_post["title"][:5]
    response = await client.get(
        POSTS_URL,
        params={"search": title_fragment},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert any(post["id"] == created_post["id"] for post in response.json()["items"])


async def test_my_posts_pagination(client: AsyncClient, auth_headers: dict, three_posts: list[dict]):
    response = await client.get(
        POSTS_URL,
        params={"skip": 0, "limit": 2},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) <= 2
    assert len(three_posts) >= 3


async def test_my_posts_unauthorized(client: AsyncClient):
    response = await client.get(POSTS_URL)

    assert response.status_code == 401


async def test_my_posts_schema(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(POSTS_URL, headers=auth_headers)
    item = response.json()["items"][0]

    assert "id" in item
    assert "title" in item
    assert "content" in item
    assert "author" in item


async def test_user_posts_success(
    client: AsyncClient,
    auth_headers: dict,
    user: dict,
    created_post: dict,
):
    response = await client.get(f"{POSTS_URL}/users/{user['id']}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(post["id"] == created_post["id"] for post in data["items"])


async def test_user_posts_author_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        f"{POSTS_URL}/users/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_user_posts_search(
    client: AsyncClient,
    auth_headers: dict,
    user: dict,
    created_post: dict,
):
    title_fragment = created_post["title"][:5]
    response = await client.get(
        f"{POSTS_URL}/users/{user['id']}",
        params={"search": title_fragment},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert any(post["id"] == created_post["id"] for post in response.json()["items"])


async def test_user_posts_pagination(
    client: AsyncClient,
    auth_headers: dict,
    user: dict,
    three_posts: list[dict],
):
    response = await client.get(
        f"{POSTS_URL}/users/{user['id']}",
        params={"skip": 0, "limit": 2},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) <= 2
    assert len(three_posts) >= 3


async def test_user_posts_unauthorized(client: AsyncClient, user: dict):
    response = await client.get(f"{POSTS_URL}/users/{user['id']}")

    assert response.status_code == 401


async def test_public_posts_success(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(PUBLIC_POSTS_URL, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert any(post["id"] == created_post["id"] for post in data["items"])


async def test_public_posts_search(client: AsyncClient, auth_headers: dict, created_post: dict):
    title_fragment = created_post["title"][:5]
    response = await client.get(
        PUBLIC_POSTS_URL,
        params={"search": title_fragment},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert any(post["id"] == created_post["id"] for post in response.json()["items"])


async def test_public_posts_pagination(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(
        PUBLIC_POSTS_URL,
        params={"skip": 0, "limit": 1},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) <= 1


async def test_public_posts_unauthorized(client: AsyncClient):
    response = await client.get(PUBLIC_POSTS_URL)

    assert response.status_code == 401


async def test_public_posts_empty_search(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        PUBLIC_POSTS_URL,
        params={"search": "zxqwerty_impossible_string_xyz"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)


async def test_get_post_success(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created_post["id"]
    assert data["title"] == created_post["title"]


async def test_get_post_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        f"{POSTS_URL}/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_get_post_invalid_uuid(client: AsyncClient, auth_headers: dict):
    response = await client.get(f"{POSTS_URL}/not-a-uuid", headers=auth_headers)

    assert response.status_code == 422


async def test_get_post_unauthorized(client: AsyncClient, created_post: dict):
    response = await client.get(f"{POSTS_URL}/{created_post['id']}")

    assert response.status_code == 401


async def test_get_post_has_like_count(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)

    data = response.json()
    assert "like_count" in data
    assert isinstance(data["like_count"], int)


async def test_get_post_has_is_liked(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.get(f"{POSTS_URL}/{created_post['id']}", headers=auth_headers)

    data = response.json()
    assert "is_liked" in data
    assert isinstance(data["is_liked"], bool)


async def test_update_post_success(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.patch(
        f"{POSTS_URL}/{created_post['id']}",
        json={"title": "Updated Title"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


async def test_update_post_partial_content(client: AsyncClient, auth_headers: dict, created_post: dict):
    new_content = "Brand new content for the post."
    response = await client.patch(
        f"{POSTS_URL}/{created_post['id']}",
        json={"content": new_content},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["content"] == new_content


async def test_update_post_not_owner(client: AsyncClient, created_post: dict):
    _, other_headers = await create_authenticated_user(client)
    response = await client.patch(
        f"{POSTS_URL}/{created_post['id']}",
        json={"title": "Hijacked"},
        headers=other_headers,
    )

    assert response.status_code in (403, 404)


async def test_update_post_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.patch(
        f"{POSTS_URL}/00000000-0000-0000-0000-000000000000",
        json={"title": "Ghost"},
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_update_post_empty_title_invalid(client: AsyncClient, auth_headers: dict, created_post: dict):
    response = await client.patch(
        f"{POSTS_URL}/{created_post['id']}",
        json={"title": ""},
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_update_post_unauthorized(client: AsyncClient, created_post: dict):
    response = await client.patch(
        f"{POSTS_URL}/{created_post['id']}",
        json={"title": "Hacked"},
    )

    assert response.status_code == 401


async def test_delete_post_success(client: AsyncClient, auth_headers: dict):
    payload = PostFactory.build()
    create_resp = await client.post(POSTS_URL, json=payload, headers=auth_headers)
    post_id = create_resp.json()["id"]

    response = await client.delete(f"{POSTS_URL}/{post_id}", headers=auth_headers)

    assert response.status_code == 204


async def test_delete_post_verifies_deletion(client: AsyncClient, auth_headers: dict):
    payload = PostFactory.build()
    create_resp = await client.post(POSTS_URL, json=payload, headers=auth_headers)
    post_id = create_resp.json()["id"]

    await client.delete(f"{POSTS_URL}/{post_id}", headers=auth_headers)
    get_resp = await client.get(f"{POSTS_URL}/{post_id}", headers=auth_headers)

    assert get_resp.status_code == 404


async def test_delete_post_not_owner(client: AsyncClient, created_post: dict):
    _, other_headers = await create_authenticated_user(client)
    response = await client.delete(
        f"{POSTS_URL}/{created_post['id']}",
        headers=other_headers,
    )

    assert response.status_code in (403, 404)


async def test_delete_post_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.delete(
        f"{POSTS_URL}/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_delete_post_unauthorized(client: AsyncClient, created_post: dict):
    response = await client.delete(f"{POSTS_URL}/{created_post['id']}")

    assert response.status_code == 401
