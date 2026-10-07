import pytest


async def _register_and_login(client, faker):
    payload = {
        "email": faker.unique.email(),
        "password": "StrongP@ssw0rd!",
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
    }
    reg = await client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201, reg.text

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return payload, token


@pytest.mark.asyncio
async def test_full_email_verification_flow(client, faker, monkeypatch):
    captured: dict[str, str] = {}

    async def fake_send_otp_code(self, *, to, purpose, code):  # noqa: ARG001 -- must match EmailService.send_otp_code's real signature
        captured["code"] = code

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send_otp_code
    )

    payload, token = await _register_and_login(client, faker)
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["is_verified"] is False

    req = await client.post("/api/v1/auth/email/verify/request", headers=headers)
    assert req.status_code == 202
    assert "code" in captured

    confirm = await client.post(
        "/api/v1/auth/email/verify/confirm",
        headers=headers,
        json={"code": captured["code"]},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["is_verified"] is True

    me_after = await client.get("/api/v1/auth/me", headers=headers)
    assert me_after.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_wrong_otp_code_is_rejected_and_counts_as_an_attempt(
    client, faker, monkeypatch
):
    captured: dict[str, str] = {}

    async def fake_send_otp_code(self, *, to, purpose, code):  # noqa: ARG001 -- must match EmailService.send_otp_code's real signature
        captured["code"] = code

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send_otp_code
    )

    _, token = await _register_and_login(client, faker)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/auth/email/verify/request", headers=headers)
    real_code = captured["code"]
    wrong_code = "000000" if real_code != "000000" else "111111"

    bad = await client.post(
        "/api/v1/auth/email/verify/confirm", headers=headers, json={"code": wrong_code}
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_otp"

    # The real code must still work afterward — one wrong guess doesn't
    # burn the legitimate code, only counts toward OTP_MAX_ATTEMPTS.
    good = await client.post(
        "/api/v1/auth/email/verify/confirm", headers=headers, json={"code": real_code}
    )
    assert good.status_code == 200, good.text


@pytest.mark.asyncio
async def test_requesting_a_new_otp_invalidates_the_previous_one(
    client, faker, monkeypatch
):
    codes: list[str] = []

    async def fake_send_otp_code(self, *, to, purpose, code):  # noqa: ARG001 -- must match EmailService.send_otp_code's real signature
        codes.append(code)

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_otp_code", fake_send_otp_code
    )

    _, token = await _register_and_login(client, faker)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/auth/email/verify/request", headers=headers)
    await client.post("/api/v1/auth/email/verify/request", headers=headers)
    assert len(codes) == 2
    first_code, second_code = codes

    # The first code is now invalidated, even though it hasn't expired.
    stale = await client.post(
        "/api/v1/auth/email/verify/confirm", headers=headers, json={"code": first_code}
    )
    assert stale.status_code == 400

    fresh = await client.post(
        "/api/v1/auth/email/verify/confirm", headers=headers, json={"code": second_code}
    )
    assert fresh.status_code == 200, fresh.text
