import time

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.factories.user_factory import UserFactory
from tests.utils.constants import LOGIN_URL, ME_URL, REGISTER_URL
from tests.utils.helpers import create_user


# ===========================================================================
# POST /auth/register
# ===========================================================================
class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        payload = UserFactory.build()
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == payload["email"]
        assert data["first_name"] == payload["first_name"]
        assert data["last_name"] == payload["last_name"]
        assert "id" in data
        assert "password" not in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = UserFactory.build()
        await client.post(REGISTER_URL, json=payload)
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient):
        payload = UserFactory.build(email="not-an-email")
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 422

    async def test_register_missing_email(self, client: AsyncClient):
        payload = UserFactory.build()
        del payload["email"]
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 422

    async def test_register_missing_password(self, client: AsyncClient):
        payload = UserFactory.build()
        del payload["password"]
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 422

    async def test_register_missing_first_name(self, client: AsyncClient):
        payload = UserFactory.build()
        del payload["first_name"]
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 422

    async def test_register_missing_last_name(self, client: AsyncClient):
        payload = UserFactory.build()
        del payload["last_name"]
        response = await client.post(REGISTER_URL, json=payload)

        assert response.status_code == 422

    async def test_register_empty_payload(self, client: AsyncClient):
        response = await client.post(REGISTER_URL, json={})

        assert response.status_code == 422

    async def test_register_response_has_no_password(self, client: AsyncClient):
        payload = UserFactory.build()
        response = await client.post(REGISTER_URL, json=payload)

        assert "password" not in response.json()


# ===========================================================================
# POST /auth/login
# ===========================================================================
class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        user = await create_user(client)
        response = await client.post(
            LOGIN_URL,
            data={"username": user["email"], "password": user["_raw_password"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    async def test_login_wrong_password(self, client: AsyncClient):
        user = await create_user(client)
        response = await client.post(
            LOGIN_URL,
            data={"username": user["email"], "password": "WrongPassword999!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post(
            LOGIN_URL,
            data={"username": "ghost@example.com", "password": "StrongP@ssw0rd!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "username, password, status_code",
        [
            ("wrong_username", "StrongP@ssw0rd!", 401),
            ("ghost@example.com", "wrong_password", 401),
            ("wrong_username", "wrong_password", 401),
            (None, "StrongP@ssw0rd!", 422),
            ("ghost@example.com", None, 422),
            (None, None, 422),
        ],
    )
    async def test_login_fail(
        self, client: AsyncClient, username, password, status_code
    ):
        response = await client.post(
            LOGIN_URL,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == status_code

    async def test_login_missing_username(self, client: AsyncClient):
        response = await client.post(
            LOGIN_URL,
            data={"password": "StrongP@ssw0rd!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 422

    async def test_login_missing_password(self, client: AsyncClient):
        response = await client.post(
            LOGIN_URL,
            data={"username": "someone@example.com"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 422

    async def test_login_empty_payload(self, client: AsyncClient):
        response = await client.post(
            LOGIN_URL,
            data={},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 422

    async def test_login_returns_jwt_structure(self, client: AsyncClient):
        """JWT must have three dot-separated base64 segments."""
        user = await create_user(client)
        response = await client.post(
            LOGIN_URL,
            data={"username": user["email"], "password": user["_raw_password"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = response.json()["access_token"]
        parts = token.split(".")
        assert len(parts) == 3


# ===========================================================================
# GET /auth/me
# ===========================================================================
class TestMe:
    async def test_me_authenticated(
        self, client: AsyncClient, auth_headers: dict, user: dict
    ):
        response = await client.get(ME_URL, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user["id"]
        assert data["email"] == user["email"]

    async def test_me_missing_token(self, client: AsyncClient):
        response = await client.get(ME_URL)

        assert response.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        response = await client.get(
            ME_URL, headers={"Authorization": "Bearer this.is.invalid"}
        )

        assert response.status_code == 401

    async def test_me_malformed_bearer(self, client: AsyncClient):
        response = await client.get(
            ME_URL, headers={"Authorization": "NotBearer sometoken"}
        )

        assert response.status_code == 401

    async def test_me_expired_token(self, client: AsyncClient):
        """A manually crafted expired token must be rejected with 401."""
        expired_payload = {
            "sub": "00000000-0000-0000-0000-000000000000",
            "exp": int(time.time()) - 3600,  # expired 1 hour ago
        }
        expired_token = jwt.encode(
            expired_payload,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        response = await client.get(
            ME_URL, headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
