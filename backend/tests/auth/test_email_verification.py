import pytest

from app.core.config import settings
from app.models.otp_code import OTPPurpose

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
VERIFY_REQUEST = "/api/v1/auth/email/verify/request"
VERIFY_CONFIRM = "/api/v1/auth/email/verify/confirm"
PASSWORD = "StrongP@ssw0rd!"


async def _register(client, faker) -> str:
    email = faker.unique.email()
    response = await client.post(
        REGISTER,
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": faker.first_name(),
            "last_name": faker.last_name(),
        },
    )
    assert response.status_code == 201, response.text
    return email


async def _login(client, email, password=PASSWORD):
    return await client.post(LOGIN, data={"username": email, "password": password})


@pytest.mark.asyncio
async def test_registering_sends_a_verification_code_to_that_address(
    client, faker, sent_codes
):
    email = await _register(client, faker)

    assert len(sent_codes) == 1
    assert sent_codes[0]["to"] == email
    assert sent_codes[0]["purpose"] == OTPPurpose.EMAIL_VERIFICATION


@pytest.mark.asyncio
async def test_login_is_refused_until_the_email_is_verified(client, faker, sent_codes):
    email = await _register(client, faker)

    response = await _login(client, email)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


@pytest.mark.asyncio
async def test_a_wrong_password_never_reveals_that_the_account_is_unverified(
    client, faker, sent_codes
):
    email = await _register(client, faker)

    response = await _login(client, email, password="WrongWrong1!")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_register_then_verify_then_login(client, faker, sent_codes):
    email = await _register(client, faker)

    confirm = await client.post(
        VERIFY_CONFIRM, json={"email": email, "code": sent_codes[0]["code"]}
    )
    assert confirm.status_code == 200, confirm.text
    # Verifying proves the inbox, not the password — no tokens handed out.
    assert "access_token" not in confirm.json()

    login = await _login(client, email)
    assert login.status_code == 200
    assert login.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_a_wrong_code_fails_but_the_right_one_still_works(
    client, faker, sent_codes
):
    email = await _register(client, faker)
    real = sent_codes[0]["code"]
    wrong = "0" * len(real) if real != "0" * len(real) else "1" * len(real)

    bad = await client.post(VERIFY_CONFIRM, json={"email": email, "code": wrong})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_otp"

    good = await client.post(VERIFY_CONFIRM, json={"email": email, "code": real})
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_resending_replaces_the_old_code(client, faker, sent_codes):
    email = await _register(client, faker)
    first = sent_codes[0]["code"]

    resend = await client.post(VERIFY_REQUEST, json={"email": email})
    assert resend.status_code == 202
    second = sent_codes[1]["code"]

    stale = await client.post(VERIFY_CONFIRM, json={"email": email, "code": first})
    assert stale.status_code == 400
    fresh = await client.post(VERIFY_CONFIRM, json={"email": email, "code": second})
    assert fresh.status_code == 200


@pytest.mark.asyncio
async def test_resend_is_silent_and_identical_for_accounts_that_dont_need_it(
    client, make_user, sent_codes
):
    verified = await make_user(is_verified=True)
    disabled = await make_user(is_verified=False, is_active=False)

    responses = [
        await client.post(VERIFY_REQUEST, json={"email": email})
        for email in ("nobody@example.com", verified.email, disabled.email)
    ]

    assert {r.status_code for r in responses} == {202}
    assert len({r.text for r in responses}) == 1  # byte-for-byte the same answer
    assert sent_codes == []


@pytest.mark.asyncio
async def test_confirming_for_an_unknown_email_looks_like_a_wrong_code(client):
    response = await client.post(
        VERIFY_CONFIRM, json={"email": "nobody@example.com", "code": "123456"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"


@pytest.mark.asyncio
async def test_an_already_verified_account_cannot_be_verified_again(client, make_user):
    user = await make_user(is_verified=True)
    response = await client.post(
        VERIFY_CONFIRM, json={"email": user.email, "code": "123456"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_the_resend_cooldown_stops_inbox_flooding(
    client, faker, sent_codes, monkeypatch
):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60)
    email = await _register(client, faker)  # sends the first code

    for _ in range(3):
        response = await client.post(VERIFY_REQUEST, json={"email": email})
        assert response.status_code == 202  # same answer — nothing to learn

    assert len(sent_codes) == 1
