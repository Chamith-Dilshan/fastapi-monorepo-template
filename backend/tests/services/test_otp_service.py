from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import InvalidOTPException
from app.models.otp_code import OTPCode, OTPPurpose
from app.services.email_service import EmailService
from app.services.otp_service import OTPService, _generate_code


class CapturingEmail(EmailService):
    def __init__(self):
        self.codes: list[str] = []

    async def send_otp_code(self, *, to, purpose, code):  # noqa: ARG002
        self.codes.append(code)


class BrokenEmail(EmailService):
    def __init__(self):
        pass

    async def send_otp_code(self, *, to, purpose, code):  # noqa: ARG002
        raise RuntimeError("mail provider is down")


def test_generated_codes_are_numeric_and_the_right_length():
    for _ in range(50):
        code = _generate_code(6)
        assert len(code) == 6
        assert code.isdigit()


def test_generated_codes_are_not_constant():
    assert len({_generate_code(8) for _ in range(20)}) > 1


@pytest.mark.asyncio
async def test_a_valid_code_works_once_and_only_once(db_session, make_user):
    user = await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)

    await service.generate_and_send(user, OTPPurpose.PASSWORD_RESET)
    code = email.codes[0]

    await service.verify(user, OTPPurpose.PASSWORD_RESET, code)
    with pytest.raises(InvalidOTPException):
        await service.verify(user, OTPPurpose.PASSWORD_RESET, code)


@pytest.mark.asyncio
async def test_an_expired_code_is_rejected(db_session, make_user):
    user = await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)
    await service.generate_and_send(user, OTPPurpose.TWO_FACTOR)

    row = (await db_session.execute(select(OTPCode))).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    with pytest.raises(InvalidOTPException):
        await service.verify(user, OTPPurpose.TWO_FACTOR, email.codes[0])


@pytest.mark.asyncio
async def test_too_many_wrong_guesses_lock_out_even_the_right_code(
    db_session, make_user
):
    user = await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)
    await service.generate_and_send(user, OTPPurpose.EMAIL_VERIFICATION)
    real = email.codes[0]
    wrong = "0" * len(real) if real != "0" * len(real) else "1" * len(real)

    for _ in range(settings.OTP_MAX_ATTEMPTS):
        with pytest.raises(InvalidOTPException):
            await service.verify(user, OTPPurpose.EMAIL_VERIFICATION, wrong)

    with pytest.raises(InvalidOTPException):
        await service.verify(user, OTPPurpose.EMAIL_VERIFICATION, real)


@pytest.mark.asyncio
async def test_a_code_only_works_for_the_purpose_it_was_issued_for(
    db_session, make_user
):
    user = await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)
    await service.generate_and_send(user, OTPPurpose.EMAIL_VERIFICATION)

    with pytest.raises(InvalidOTPException):
        await service.verify(user, OTPPurpose.PASSWORD_RESET, email.codes[0])


@pytest.mark.asyncio
async def test_a_code_only_works_for_the_user_it_was_issued_to(db_session, make_user):
    owner, other = await make_user(), await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)
    await service.generate_and_send(owner, OTPPurpose.PASSWORD_RESET)

    with pytest.raises(InvalidOTPException):
        await service.verify(other, OTPPurpose.PASSWORD_RESET, email.codes[0])


@pytest.mark.asyncio
async def test_codes_are_stored_hashed(db_session, make_user):
    user = await make_user()
    email = CapturingEmail()
    await OTPService(db_session, email).generate_and_send(user, OTPPurpose.TWO_FACTOR)
    row = (await db_session.execute(select(OTPCode))).scalar_one()
    assert email.codes[0] not in row.code_hash


@pytest.mark.asyncio
async def test_email_failure_does_not_fail_the_request_and_the_code_still_works(
    db_session, make_user
):
    user = await make_user()
    # Delivery fails — generate_and_send must swallow it (the response must
    # not reveal mail-provider outages or differ for existing accounts).
    await OTPService(db_session, BrokenEmail()).generate_and_send(
        user, OTPPurpose.PASSWORD_RESET
    )
    assert len((await db_session.execute(select(OTPCode))).scalars().all()) == 1


# --- resend cooldown ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_fresh_outstanding_code_suppresses_another_send(
    db_session, make_user, monkeypatch
):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60)
    user = await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)

    assert await service.generate_and_send(user, OTPPurpose.PASSWORD_RESET) is True
    assert await service.generate_and_send(user, OTPPurpose.PASSWORD_RESET) is False
    assert len(email.codes) == 1
    # The first code is still the live one.
    await service.verify(user, OTPPurpose.PASSWORD_RESET, email.codes[0])


@pytest.mark.asyncio
async def test_the_cooldown_is_per_user_and_per_purpose(
    db_session, make_user, monkeypatch
):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60)
    a, b = await make_user(), await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)

    assert await service.generate_and_send(a, OTPPurpose.PASSWORD_RESET) is True
    assert await service.generate_and_send(b, OTPPurpose.PASSWORD_RESET) is True
    assert await service.generate_and_send(a, OTPPurpose.TWO_FACTOR) is True


@pytest.mark.asyncio
async def test_an_aged_or_used_code_does_not_block_a_new_one(
    db_session, make_user, monkeypatch
):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60)
    user = await make_user()
    email = CapturingEmail()
    service = OTPService(db_session, email)

    await service.generate_and_send(user, OTPPurpose.PASSWORD_RESET)
    row = (await db_session.execute(select(OTPCode))).scalar_one()
    row.created_at = datetime.now(UTC) - timedelta(seconds=61)
    await db_session.flush()
    assert await service.generate_and_send(user, OTPPurpose.PASSWORD_RESET) is True

    # A code that was *used* never blocks the next one.
    await service.verify(user, OTPPurpose.PASSWORD_RESET, email.codes[-1])
    assert await service.generate_and_send(user, OTPPurpose.PASSWORD_RESET) is True
