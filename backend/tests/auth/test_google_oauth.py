import pytest

from app.models.oauth_account import OAuthProvider
from app.services.oauth_service import OAuthProfile, OAuthService


def _fake_profile(**overrides) -> OAuthProfile:
    defaults = {
        "provider_account_id": "google-sub-12345",
        "email": "newuser@example.com",
        "email_verified": True,
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    defaults.update(overrides)
    return OAuthProfile(**defaults)


@pytest.mark.asyncio
async def test_new_google_user_is_created_verified_with_no_password(db_session):
    service = OAuthService(db_session)
    profile = _fake_profile()

    user, is_new = await service.find_or_create_user(OAuthProvider.GOOGLE, profile)

    assert is_new is True
    assert user.email == profile.email
    assert user.is_verified is True  # Google already verified it
    assert user.hashed_password is None  # OAuth-only account
    assert user.first_name == "Ada"


@pytest.mark.asyncio
async def test_second_login_from_same_google_account_reuses_user(db_session):
    service = OAuthService(db_session)
    profile = _fake_profile()

    first_user, first_is_new = await service.find_or_create_user(OAuthProvider.GOOGLE, profile)
    second_user, second_is_new = await service.find_or_create_user(OAuthProvider.GOOGLE, profile)

    assert first_is_new is True
    assert second_is_new is False
    assert first_user.id == second_user.id


@pytest.mark.asyncio
async def test_google_signin_links_to_existing_password_account_by_email(
    db_session, faker
):
    # A user who already registered with a password...
    from app.dtos.user_dto import UserCreateRequest
    from app.services.user_service import UserService

    existing_email = faker.unique.email()
    user_service = UserService(db_session)
    existing = await user_service.create_user(
        UserCreateRequest(
            email=existing_email,
            password="StrongP@ssw0rd!",
            first_name="Original",
            last_name="Name",
        )
    )

    # ...then signs in with Google using the same email. Same account,
    # not a duplicate — and the original password-based login must still
    # work afterward (linking must not clobber hashed_password).
    oauth_service = OAuthService(db_session)
    profile = _fake_profile(email=existing_email)
    linked_user, is_new = await oauth_service.find_or_create_user(OAuthProvider.GOOGLE, profile)

    assert is_new is False
    assert linked_user.id == existing.id
    assert linked_user.hashed_password is not None

    still_works = await user_service.authenticate_user(existing_email, "StrongP@ssw0rd!")
    assert still_works.id == existing.id


@pytest.mark.asyncio
async def test_callback_rejects_mismatched_state(client):
    client.cookies.set("oauth_state", "cookie-value")
    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "irrelevant", "state": "different-value"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_callback_rejects_missing_state_cookie(client):
    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "irrelevant", "state": "whatever"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_full_callback_flow_issues_a_working_token(client, monkeypatch):
    profile = _fake_profile(email="callback-flow@example.com")

    async def fake_exchange(self, code):  # noqa: ARG001 -- must match the instance method's signature
        assert code == "the-auth-code"
        return profile

    monkeypatch.setattr(
        "app.services.oauth_service.GoogleOAuthService.exchange_code_for_profile",
        fake_exchange,
    )

    client.cookies.set("oauth_state", "matching-state")
    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "the-auth-code", "state": "matching-state"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("http://localhost:3000/auth/callback?access_token=")

    token = location.split("access_token=", 1)[1]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "callback-flow@example.com"
