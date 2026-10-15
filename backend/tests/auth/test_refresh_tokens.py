from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.refresh_token import RefreshToken


async def _refresh(client, token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


@pytest.mark.asyncio
async def test_login_returns_a_refresh_token(make_user, login):
    tokens = await login(await make_user())
    assert tokens["refresh_token"]
    assert tokens["access_token"]
    assert tokens["two_factor_required"] is False


@pytest.mark.asyncio
async def test_refresh_rotates_the_pair_and_the_new_access_token_works(
    client, make_user, login
):
    user = await make_user()
    first = await login(user)

    response = await _refresh(client, first["refresh_token"])
    assert response.status_code == 200, response.text
    second = response.json()

    assert second["refresh_token"] != first["refresh_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {second['access_token']}"}
    )
    assert me.json()["email"] == user.email


@pytest.mark.asyncio
async def test_replaying_a_rotated_token_revokes_the_whole_family(
    client, make_user, login
):
    first = await login(await make_user())
    second = (await _refresh(client, first["refresh_token"])).json()

    # The *old* token shows up again: someone is replaying a stolen copy.
    replay = await _refresh(client, first["refresh_token"])
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_reuse"

    # ...and the legitimate newest token from that same login is now dead too,
    # so whoever holds it (thief or owner) must sign in again.
    after = await _refresh(client, second["refresh_token"])
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_separate_logins_are_separate_families(client, make_user, login):
    user = await make_user()
    laptop = await login(user)
    phone = await login(user)

    await _refresh(client, laptop["refresh_token"])
    replay = await _refresh(client, laptop["refresh_token"])
    assert replay.status_code == 401

    # Burning the laptop's family must not sign the phone out.
    assert (await _refresh(client, phone["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_unknown_refresh_token_is_rejected(client):
    response = await _refresh(client, "definitely-not-a-real-token")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(client, db_session, make_user, login):
    tokens = await login(await make_user())
    record = (await db_session.execute(select(RefreshToken))).scalar_one()
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_refresh_is_refused_for_a_deactivated_user(client, make_user, login):
    user = await make_user()
    tokens = await login(user)
    user.is_active = False

    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_refresh_tokens_are_stored_hashed(db_session, make_user, login):
    tokens = await login(await make_user())
    record = (await db_session.execute(select(RefreshToken))).scalar_one()
    assert record.token_hash != tokens["refresh_token"]
    assert len(record.token_hash) == 64  # SHA-256 hex


# --- logout -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_kills_the_refresh_token(client, make_user, login):
    tokens = await login(await make_user())

    out = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert out.status_code == 204
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_logout_with_an_unknown_token_is_still_204(client):
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": "nope"})
    assert out.status_code == 204


# --- sessions ended by password changes ---------------------------------------


@pytest.mark.asyncio
async def test_password_change_ends_other_sessions_but_keeps_this_one(
    client, make_user, login
):
    user = await make_user()
    other_session = await login(user)
    this_session = await login(user)

    response = await client.post(
        "/api/v1/auth/password/change",
        headers={"Authorization": f"Bearer {this_session['access_token']}"},
        json={"current_password": "StrongP@ssw0rd!", "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 200, response.text
    fresh = response.json()

    assert (await _refresh(client, other_session["refresh_token"])).status_code == 401
    assert (await _refresh(client, this_session["refresh_token"])).status_code == 401
    assert (await _refresh(client, fresh["refresh_token"])).status_code == 200

    relogin = await client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": "BrandNewPass1!"},
    )
    assert relogin.status_code == 200


@pytest.mark.asyncio
async def test_password_change_with_wrong_current_password_is_400(
    client, make_user, auth_headers
):
    user = await make_user()
    response = await client.post(
        "/api/v1/auth/password/change",
        headers=await auth_headers(user),
        json={"current_password": "WrongWrong1!", "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_password"


@pytest.mark.asyncio
async def test_oauth_only_account_cannot_use_password_change(client, make_user):
    from app.core.security import create_access_token

    user = await make_user(password=None)
    token = create_access_token(data={"sub": str(user.id)})
    response = await client.post(
        "/api/v1/auth/password/change",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "anything", "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_password_reset_ends_every_session(client, make_user, login, monkeypatch):
    captured = {}

    async def fake_send(self, *, to, purpose, code):
        captured["code"] = code

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send
    )

    user = await make_user()
    tokens = await login(user)

    await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": user.email, "purpose": "password_reset"},
    )
    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={
            "email": user.email,
            "code": captured["code"],
            "new_password": "BrandNewPass1!",
        },
    )
    assert reset.status_code == 200
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401
