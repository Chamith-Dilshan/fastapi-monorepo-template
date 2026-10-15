import pytest
from sqlalchemy import select

from app.dtos.user_dto import UserCreateRequest
from app.models.oauth_account import OAuthAccount, OAuthProvider
from app.services.oauth_service import OAuthProfile, OAuthService
from app.services.user_service import UserService


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


def _patch_google(monkeypatch, profile):
    async def fake_exchange(self, code):
        return profile

    monkeypatch.setattr(
        "app.services.oauth_service.GoogleOAuthService.exchange_code_for_profile",
        fake_exchange,
    )


async def _callback(client, profile, monkeypatch):
    _patch_google(monkeypatch, profile)
    client.cookies.set("oauth_state", "matching-state")
    return await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "google-auth-code", "state": "matching-state"},
        follow_redirects=False,
    )


# --- find_or_create_user ----------------------------------------------------


@pytest.mark.asyncio
async def test_new_google_user_is_created_verified_with_no_password(db_session):
    user, is_new = await OAuthService(db_session).find_or_create_user(
        OAuthProvider.GOOGLE, _fake_profile()
    )
    assert is_new is True
    assert user.is_verified is True  # Google already verified it
    assert user.hashed_password is None  # OAuth-only account
    assert user.first_name == "Ada"


@pytest.mark.asyncio
async def test_missing_names_fall_back_to_the_email_local_part(db_session):
    user, _ = await OAuthService(db_session).find_or_create_user(
        OAuthProvider.GOOGLE, _fake_profile(first_name="", last_name="")
    )
    assert user.first_name == "newuser"
    assert user.last_name == ""


@pytest.mark.asyncio
async def test_second_login_from_same_google_account_reuses_user(db_session):
    service = OAuthService(db_session)
    first, first_new = await service.find_or_create_user(
        OAuthProvider.GOOGLE, _fake_profile()
    )
    second, second_new = await service.find_or_create_user(
        OAuthProvider.GOOGLE, _fake_profile()
    )
    assert (first_new, second_new) == (True, False)
    assert first.id == second.id


@pytest.mark.asyncio
async def test_linking_to_a_verified_password_account_keeps_the_password(
    db_session, make_user
):
    existing = await make_user(is_verified=True)
    user, is_new = await OAuthService(db_session).find_or_create_user(
        OAuthProvider.GOOGLE, _fake_profile(email=existing.email)
    )
    assert is_new is False
    assert user.id == existing.id
    assert user.hashed_password is not None
    assert (
        await UserService(db_session).authenticate_user(
            existing.email, "StrongP@ssw0rd!"
        )
    ).id == existing.id


@pytest.mark.asyncio
async def test_linking_to_an_unverified_account_discards_its_password(
    db_session, faker
):
    """Pre-hijacking: a stranger registers victim@example.com with their own
    password before the real owner ever signs up. When the real owner signs
    in with Google, the stranger's password must not survive."""
    email = faker.unique.email()
    await UserService(db_session).create_user(
        UserCreateRequest(
            email=email, password="AttackerChosen1!", first_name="Eve", last_name="X"
        )
    )

    user, _ = await OAuthService(db_session).find_or_create_user(
        OAuthProvider.GOOGLE, _fake_profile(email=email)
    )

    assert user.hashed_password is None
    assert user.is_verified is True
    with pytest.raises(Exception, match="Invalid credentials"):
        await UserService(db_session).authenticate_user(email, "AttackerChosen1!")


@pytest.mark.asyncio
async def test_unverified_google_email_is_never_linked_to_an_existing_account(
    db_session, make_user
):
    existing = await make_user()
    with pytest.raises(Exception, match="Google sign-in failed"):
        await OAuthService(db_session).find_or_create_user(
            OAuthProvider.GOOGLE,
            _fake_profile(email=existing.email, email_verified=False),
        )
    links = (await db_session.execute(select(OAuthAccount))).scalars().all()
    assert links == []


@pytest.mark.asyncio
async def test_disabled_accounts_cannot_sign_in_with_google(db_session, make_user):
    existing = await make_user(is_active=False)
    with pytest.raises(Exception, match="disabled"):
        await OAuthService(db_session).find_or_create_user(
            OAuthProvider.GOOGLE, _fake_profile(email=existing.email)
        )


# --- the HTTP flow ------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_redirects_to_google_with_a_matching_state_cookie(client):
    response = await client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    state = response.cookies["oauth_state"]
    assert f"state={state}" in location


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
        "/api/v1/auth/google/callback", params={"code": "x", "state": "whatever"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_callback_puts_a_one_time_code_in_the_url_never_a_token(
    client, monkeypatch
):
    response = await _callback(client, _fake_profile(), monkeypatch)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("http://localhost:3000/auth/callback?code=")
    assert "access_token" not in location
    assert "refresh_token" not in location


@pytest.mark.asyncio
async def test_exchange_code_yields_working_tokens_exactly_once(client, monkeypatch):
    response = await _callback(
        client, _fake_profile(email="callback-flow@example.com"), monkeypatch
    )
    code = response.headers["location"].split("code=", 1)[1]

    exchanged = await client.post("/api/v1/auth/oauth/exchange", json={"code": code})
    assert exchanged.status_code == 200, exchanged.text
    tokens = exchanged.json()
    assert tokens["refresh_token"]

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.json()["email"] == "callback-flow@example.com"

    replay = await client.post("/api/v1/auth/oauth/exchange", json={"code": code})
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "invalid_otp"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_code",
    [
        "garbage",
        "not-a-uuid.secret",
        "00000000-0000-0000-0000-000000000000.secret",
    ],
)
async def test_exchange_rejects_malformed_or_unknown_codes(client, bad_code):
    response = await client.post("/api/v1/auth/oauth/exchange", json={"code": bad_code})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"


@pytest.mark.asyncio
async def test_exchange_code_for_a_since_disabled_user_is_rejected(
    client, db_session, monkeypatch
):
    response = await _callback(client, _fake_profile(), monkeypatch)
    code = response.headers["location"].split("code=", 1)[1]

    user = await UserService(db_session).get_user_by_email("newuser@example.com")
    assert user is not None
    user.is_active = False
    await db_session.flush()

    exchanged = await client.post("/api/v1/auth/oauth/exchange", json={"code": code})
    assert exchanged.status_code == 400
