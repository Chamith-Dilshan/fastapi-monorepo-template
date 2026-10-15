import pytest

from app.models.otp_code import OTPPurpose

BASE = "/api/v1/auth"


async def _enable_2fa(client, headers, sent_codes):
    await client.post(f"{BASE}/2fa/enable/request", headers=headers)
    confirm = await client.post(
        f"{BASE}/2fa/enable/confirm",
        headers=headers,
        json={"code": sent_codes[-1]["code"]},
    )
    assert confirm.status_code == 200, confirm.text


@pytest.mark.asyncio
async def test_login_without_2fa_returns_tokens_directly(make_user, login):
    body = await login(await make_user())
    assert body["two_factor_required"] is False
    assert body["access_token"]


@pytest.mark.asyncio
async def test_enabling_2fa_needs_a_confirmed_code(
    client, make_user, auth_headers, sent_codes
):
    headers = await auth_headers(await make_user())

    request = await client.post(f"{BASE}/2fa/enable/request", headers=headers)
    assert request.status_code == 202
    assert sent_codes[-1]["purpose"] == OTPPurpose.TWO_FACTOR

    wrong = await client.post(
        f"{BASE}/2fa/enable/confirm", headers=headers, json={"code": "000000"}
    )
    assert wrong.status_code == 400
    assert (await client.get(f"{BASE}/me", headers=headers)).json()[
        "is_2fa_enabled"
    ] is False

    good = await client.post(
        f"{BASE}/2fa/enable/confirm",
        headers=headers,
        json={"code": sent_codes[-1]["code"]},
    )
    assert good.status_code == 200
    assert good.json()["is_2fa_enabled"] is True


@pytest.mark.asyncio
async def test_a_2fa_account_gets_no_tokens_until_the_second_step(
    client, make_user, auth_headers, sent_codes
):
    user = await make_user()
    await _enable_2fa(client, await auth_headers(user), sent_codes)

    login = await client.post(
        f"{BASE}/login", data={"username": user.email, "password": "StrongP@ssw0rd!"}
    )
    body = login.json()
    assert login.status_code == 200
    assert body["two_factor_required"] is True
    assert body.get("access_token") is None
    assert body.get("refresh_token") is None

    verify = await client.post(
        f"{BASE}/2fa/verify", json={"email": user.email, "code": sent_codes[-1]["code"]}
    )
    assert verify.status_code == 200, verify.text
    assert verify.json()["access_token"]
    assert verify.json()["refresh_token"]


@pytest.mark.asyncio
async def test_2fa_verify_with_a_wrong_code_or_unknown_email_is_invalid_otp(
    client, make_user
):
    user = await make_user()
    for email in (user.email, "nobody@example.com"):
        response = await client.post(
            f"{BASE}/2fa/verify", json={"email": email, "code": "123456"}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_otp"


@pytest.mark.asyncio
async def test_disabling_2fa_requires_the_current_password(
    client, make_user, auth_headers, sent_codes
):
    user = await make_user()
    headers = await auth_headers(user)
    await _enable_2fa(client, headers, sent_codes)

    wrong = await client.post(
        f"{BASE}/2fa/disable", headers=headers, json={"password": "TotallyWrong!1"}
    )
    # 400, not 401: the session is fine, only this confirmation was wrong.
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "invalid_password"

    right = await client.post(
        f"{BASE}/2fa/disable", headers=headers, json={"password": "StrongP@ssw0rd!"}
    )
    assert right.status_code == 200
    assert right.json()["is_2fa_enabled"] is False

    login = await client.post(
        f"{BASE}/login", data={"username": user.email, "password": "StrongP@ssw0rd!"}
    )
    assert login.json()["two_factor_required"] is False
    assert login.json()["access_token"]
