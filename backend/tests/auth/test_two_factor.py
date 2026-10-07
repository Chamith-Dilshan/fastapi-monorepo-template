import pytest


async def _register_and_login(client, faker, password="StrongP@ssw0rd!"):
    payload = {
        "email": faker.unique.email(),
        "password": password,
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
    }
    reg = await client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201, reg.text

    login = await client.post(
        "/api/v1/auth/login", data={"username": payload["email"], "password": payload["password"]}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return payload, token


def _capture_otp(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_send_otp_code(self, *, to, purpose, code):  # noqa: ARG001 -- must match EmailService.send_otp_code's real signature
        captured["code"] = code

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send_otp_code
    )
    return captured


@pytest.mark.asyncio
async def test_login_without_2fa_returns_token_directly(client, faker):
    payload, token = await _register_and_login(client, faker)
    assert token is not None


@pytest.mark.asyncio
async def test_enabling_2fa_requires_a_confirmed_code(client, faker, monkeypatch):
    captured = _capture_otp(monkeypatch)
    _, token = await _register_and_login(client, faker)
    headers = {"Authorization": f"Bearer {token}"}

    req = await client.post("/api/v1/auth/2fa/enable/request", headers=headers)
    assert req.status_code == 202

    # Wrong code doesn't enable it.
    bad = await client.post(
        "/api/v1/auth/2fa/enable/confirm", headers=headers, json={"code": "000000"}
    )
    assert bad.status_code == 400

    me_still_off = await client.get("/api/v1/auth/me", headers=headers)
    assert me_still_off.json()["is_2fa_enabled"] is False

    good = await client.post(
        "/api/v1/auth/2fa/enable/confirm", headers=headers, json={"code": captured["code"]}
    )
    assert good.status_code == 200, good.text


@pytest.mark.asyncio
async def test_full_2fa_login_flow(client, faker, monkeypatch):
    captured = _capture_otp(monkeypatch)
    payload, token = await _register_and_login(client, faker)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/auth/2fa/enable/request", headers=headers)
    await client.post(
        "/api/v1/auth/2fa/enable/confirm", headers=headers, json={"code": captured["code"]}
    )

    # Now a normal login does NOT return a token — it asks for the second step.
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["two_factor_required"] is True
    assert body.get("access_token") is None

    # The 2FA code from the login attempt (not the enable-confirm code,
    # which was already consumed) finishes the login.
    verify = await client.post(
        "/api/v1/auth/2fa/verify",
        json={"email": payload["email"], "code": captured["code"]},
    )
    assert verify.status_code == 200, verify.text
    assert "access_token" in verify.json()


@pytest.mark.asyncio
async def test_disabling_2fa_requires_current_password(client, faker, monkeypatch):
    captured = _capture_otp(monkeypatch)
    payload, token = await _register_and_login(client, faker)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/auth/2fa/enable/request", headers=headers)
    await client.post(
        "/api/v1/auth/2fa/enable/confirm", headers=headers, json={"code": captured["code"]}
    )

    wrong = await client.post(
        "/api/v1/auth/2fa/disable", headers=headers, json={"password": "TotallyWrong!1"}
    )
    assert wrong.status_code == 401

    right = await client.post(
        "/api/v1/auth/2fa/disable", headers=headers, json={"password": payload["password"]}
    )
    assert right.status_code == 200, right.text

    # 2FA is off again — a normal login returns a token directly.
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    assert login.json()["two_factor_required"] is False
    assert login.json()["access_token"] is not None
