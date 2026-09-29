import pytest
from httpx import AsyncClient

from tests.utils.constants import USERS_URL
from tests.utils.helpers import create_authenticated_user


async def test_list_users_success(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.get(USERS_URL, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1


async def test_list_users_pagination(client: AsyncClient, auth_headers: dict):
    for _ in range(3):
        await create_authenticated_user(client)

    response = await client.get(
        USERS_URL,
        params={"skip": 0, "limit": 2},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) <= 2


async def test_list_users_pagination_skip(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        USERS_URL,
        params={"skip": 1, "limit": 1},
        headers=auth_headers,
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({"limit": 0}, 422),
        ({"limit": 101}, 422),
        ({"skip": -1}, 422),
    ],
)
async def test_list_users_invalid_queries(
    client: AsyncClient,
    auth_headers: dict,
    params: dict,
    expected_status: int,
):
    response = await client.get(USERS_URL, params=params, headers=auth_headers)

    assert response.status_code == expected_status


async def test_list_users_unauthorized(client: AsyncClient):
    response = await client.get(USERS_URL)

    assert response.status_code == 401


async def test_list_users_schema(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.get(USERS_URL, headers=auth_headers)

    item = response.json()["items"][0]
    assert "id" in item
    assert "email" in item
    assert "first_name" in item
    assert "last_name" in item
    assert "password" not in item


async def test_get_user_success(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.get(f"{USERS_URL}/{user['id']}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user["id"]
    assert data["email"] == user["email"]


async def test_get_user_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        f"{USERS_URL}/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_get_user_invalid_uuid(client: AsyncClient, auth_headers: dict):
    response = await client.get(f"{USERS_URL}/not-a-uuid", headers=auth_headers)

    assert response.status_code == 422


async def test_get_user_unauthorized(client: AsyncClient, user: dict):
    response = await client.get(f"{USERS_URL}/{user['id']}")

    assert response.status_code == 401


async def test_get_user_response_has_no_password(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.get(f"{USERS_URL}/{user['id']}", headers=auth_headers)

    assert "password" not in response.json()


async def test_update_user_success(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.patch(
        f"{USERS_URL}/{user['id']}",
        json={"first_name": "UpdatedName"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["first_name"] == "UpdatedName"


async def test_update_user_partial_last_name(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.patch(
        f"{USERS_URL}/{user['id']}",
        json={"last_name": "UpdatedLast"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["last_name"] == "UpdatedLast"


async def test_update_user_password_too_short(client: AsyncClient, auth_headers: dict, user: dict):
    response = await client.patch(
        f"{USERS_URL}/{user['id']}",
        json={"password": "short"},
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_update_user_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.patch(
        f"{USERS_URL}/00000000-0000-0000-0000-000000000000",
        json={"first_name": "Ghost"},
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_update_user_unauthorized(client: AsyncClient, user: dict):
    response = await client.patch(
        f"{USERS_URL}/{user['id']}",
        json={"first_name": "Hack"},
    )

    assert response.status_code == 401


async def test_update_user_returns_updated_data(client: AsyncClient, auth_headers: dict, user: dict):
    new_first = "ChangedFirst"
    new_last = "ChangedLast"
    response = await client.patch(
        f"{USERS_URL}/{user['id']}",
        json={"first_name": new_first, "last_name": new_last},
        headers=auth_headers,
    )

    data = response.json()
    assert data["first_name"] == new_first
    assert data["last_name"] == new_last
    assert data["id"] == user["id"]


async def test_delete_user_success(client: AsyncClient):
    user, headers = await create_authenticated_user(client)
    response = await client.delete(f"{USERS_URL}/{user['id']}", headers=headers)

    assert response.status_code == 204


async def test_delete_user_verifies_deletion(client: AsyncClient, auth_headers: dict):
    new_user, new_headers = await create_authenticated_user(client)
    await client.delete(f"{USERS_URL}/{new_user['id']}", headers=new_headers)

    get_response = await client.get(
        f"{USERS_URL}/{new_user['id']}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404


async def test_delete_user_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.delete(
        f"{USERS_URL}/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_delete_user_unauthorized(client: AsyncClient, user: dict):
    response = await client.delete(f"{USERS_URL}/{user['id']}")

    assert response.status_code == 401
