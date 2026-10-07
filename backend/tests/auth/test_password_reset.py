import pytest


async def _register(client, faker, password="StrongP@ssw0rd!"):
    payload = {
        "email": faker.unique.email(),
        "password": password,
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
    }
    reg = await client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    return payload


@pytest.mark.asyncio
async def test_full_password_reset_flow(client, faker, monkeypatch):
    captured: dict[str, str] = {}

    async def fake_send_otp_code(self, *, to, purpose, code):  # noqa: ARG001 -- must match EmailService.send_otp_code's real signature
        captured["code"] = code

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send_otp_code
    )

    payload = await _register(client, faker)

    forgot = await client.post(
        "/api/v1/auth/password/forgot", json={"email": payload["email"], "purpose": "password_reset"}
    )
    assert forgot.status_code == 202
    assert "code" in captured

    new_password = "EvenStronger!42"
    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"email": payload["email"], "code": captured["code"], "new_password": new_password},
    )
    assert reset.status_code == 200, reset.text

    # Old password no longer works.
    old_login = await client.post(
        "/api/v1/auth/login",
        data={"username": payload["email"], "password": payload["password"]},
    )
    assert old_login.status_code == 401

    # New password does.
    new_login = await client.post(
        "/api/v1/auth/login",
        data={"username": payload["email"], "password": new_password},
    )
    assert new_login.status_code == 200, new_login.text
    assert "access_token" in new_login.json()


@pytest.mark.asyncio
async def test_forgot_password_does_not_reveal_whether_email_exists(client):
    response = await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "nobody-at-all@example.com", "purpose": "password_reset"},
    )
    # Same 202 a real email gets — see test_full_password_reset_flow.
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_reset_with_wrong_code_fails(client, faker, monkeypatch):
    async def fake_send_otp_code(self, *, to, purpose, code):  # noqa: ARG001 -- must match EmailService.send_otp_code's real signature
        pass

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send_otp_code
    )

    payload = await _register(client, faker)
    await client.post(
        "/api/v1/auth/password/forgot", json={"email": payload["email"], "purpose": "password_reset"}
    )

    response = await client.post(
        "/api/v1/auth/password/reset",
        json={"email": payload["email"], "code": "000000", "new_password": "WhateverNew1!"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"
