import pytest

from app.models.otp_code import OTPPurpose

FORGOT = "/api/v1/auth/password/forgot"
RESET = "/api/v1/auth/password/reset"
LOGIN = "/api/v1/auth/login"
OLD = "StrongP@ssw0rd!"
NEW = "EvenStronger!42"


@pytest.mark.asyncio
async def test_full_password_reset_flow(client, make_user, sent_codes):
    user = await make_user()

    forgot = await client.post(FORGOT, json={"email": user.email})
    assert forgot.status_code == 202
    assert sent_codes[0]["purpose"] == OTPPurpose.PASSWORD_RESET

    reset = await client.post(
        RESET,
        json={"email": user.email, "code": sent_codes[0]["code"], "new_password": NEW},
    )
    assert reset.status_code == 200, reset.text

    old = await client.post(LOGIN, data={"username": user.email, "password": OLD})
    assert old.status_code == 401
    new = await client.post(LOGIN, data={"username": user.email, "password": NEW})
    assert new.status_code == 200
    assert new.json()["access_token"]


@pytest.mark.asyncio
async def test_forgot_password_does_not_reveal_whether_the_email_exists(
    client, sent_codes
):
    response = await client.post(FORGOT, json={"email": "nobody-at-all@example.com"})
    assert response.status_code == 202  # same answer a real account gets
    assert sent_codes == []


@pytest.mark.asyncio
async def test_reset_with_a_wrong_code_fails(client, make_user, sent_codes):
    user = await make_user()
    await client.post(FORGOT, json={"email": user.email})
    real = sent_codes[0]["code"]
    wrong = "0" * len(real) if real != "0" * len(real) else "1" * len(real)

    response = await client.post(
        RESET, json={"email": user.email, "code": wrong, "new_password": NEW}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"


@pytest.mark.asyncio
async def test_reset_for_an_unknown_email_looks_like_a_wrong_code(client):
    response = await client.post(
        RESET,
        json={"email": "nobody@example.com", "code": "123456", "new_password": NEW},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"


@pytest.mark.asyncio
async def test_a_reset_code_cannot_be_used_twice(client, make_user, sent_codes):
    user = await make_user()
    await client.post(FORGOT, json={"email": user.email})
    body = {"email": user.email, "code": sent_codes[0]["code"], "new_password": NEW}

    assert (await client.post(RESET, json=body)).status_code == 200
    assert (await client.post(RESET, json=body)).status_code == 400


@pytest.mark.asyncio
async def test_resetting_also_verifies_an_unverified_account(
    client, make_user, sent_codes
):
    """Whoever completes a reset held the emailed code, i.e. the inbox — so
    someone who registered, never verified and forgot can recover through
    here instead of being stuck."""
    user = await make_user(is_verified=False)
    blocked = await client.post(LOGIN, data={"username": user.email, "password": OLD})
    assert blocked.status_code == 403

    await client.post(FORGOT, json={"email": user.email})
    await client.post(
        RESET,
        json={"email": user.email, "code": sent_codes[0]["code"], "new_password": NEW},
    )

    login = await client.post(LOGIN, data={"username": user.email, "password": NEW})
    assert login.status_code == 200
