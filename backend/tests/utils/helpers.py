from httpx import AsyncClient

from tests.factories.user_factory import UserFactory
from tests.utils.constants import LOGIN_URL, REGISTER_URL


async def create_user(client: AsyncClient, **overrides) -> dict:
    """Register a user via the API and return the response JSON."""
    data = UserFactory.build(**overrides)
    payload = {
        "email": data["email"],
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "password": data["password"],
    }
    response = await client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201, response.text
    user = response.json()
    # Stash the raw password so callers can log in
    user["_raw_password"] = data["password"]
    return user


async def login_user(client: AsyncClient, email: str, password: str) -> str:
    """Login and return the raw JWT access token string."""
    response = await client.post(
        LOGIN_URL,
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def authenticated_headers(
    client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    """Return Authorization headers for a registered email/password pair."""
    token = await login_user(client, email, password)
    return {"Authorization": f"Bearer {token}"}


async def create_authenticated_user(
    client: AsyncClient, **overrides
) -> tuple[dict, dict[str, str]]:
    """
    Register a new user and return (user_dict, auth_headers).
    """
    user = await create_user(client, **overrides)
    headers = await authenticated_headers(client, user["email"], user["_raw_password"])
    return user, headers
