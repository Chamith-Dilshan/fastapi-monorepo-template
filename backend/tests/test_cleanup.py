from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.cleanup import run_cleanup
from app.core.audit import record_audit_event
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.otp_code import OTPCode, OTPPurpose
from app.models.refresh_token import RefreshToken
from app.models.user import User


def _ago(**kwargs) -> datetime:
    return datetime.now(UTC) - timedelta(**kwargs)


async def _all(session, model):
    return (await session.execute(select(model))).scalars().all()


def _token(user, *, expires_at, revoked_at=None, name="t") -> RefreshToken:
    return RefreshToken(
        user_id=user.id,
        family_id=uuid4(),
        token_hash=f"{name}-{uuid4().hex}".ljust(64, "0")[:64],
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


@pytest.mark.asyncio
async def test_expired_refresh_tokens_go_but_live_and_revoked_ones_stay(
    db_session, make_user
):
    user = await make_user()
    expired = _token(user, expires_at=_ago(days=2), name="expired")
    live = _token(user, expires_at=datetime.now(UTC) + timedelta(days=5), name="live")
    # Revoked but not yet expired: reuse detection needs this row to still
    # exist, so a replay of it is recognised as theft instead of "unknown".
    revoked = _token(
        user,
        expires_at=datetime.now(UTC) + timedelta(days=5),
        revoked_at=_ago(hours=1),
        name="revoked",
    )
    just_expired = _token(user, expires_at=_ago(hours=1), name="grace")
    db_session.add_all([expired, live, revoked, just_expired])
    await db_session.flush()

    removed = await run_cleanup(db_session)

    assert removed["refresh_tokens"] == 1
    kept = {t.id for t in await _all(db_session, RefreshToken)}
    assert kept == {live.id, revoked.id, just_expired.id}  # grace period respected


@pytest.mark.asyncio
async def test_expired_one_time_codes_go_whether_used_or_not(db_session, make_user):
    user = await make_user()

    def code(**kw) -> OTPCode:
        return OTPCode(
            user_id=user.id, purpose=OTPPurpose.PASSWORD_RESET, code_hash="x", **kw
        )

    old_unused = code(expires_at=_ago(days=3))
    old_used = code(expires_at=_ago(days=3), consumed_at=_ago(days=3))
    fresh = code(expires_at=datetime.now(UTC) + timedelta(minutes=5))
    db_session.add_all([old_unused, old_used, fresh])
    await db_session.flush()

    removed = await run_cleanup(db_session)

    assert removed["otp_codes"] == 2
    assert [c.id for c in await _all(db_session, OTPCode)] == [fresh.id]


@pytest.mark.asyncio
async def test_only_stale_unverified_accounts_are_removed(db_session, make_user):
    stale = await make_user(is_verified=False)
    recent = await make_user(is_verified=False)
    old_but_verified = await make_user(is_verified=True)
    stale.created_at = _ago(days=settings.UNVERIFIED_USER_TTL_DAYS + 1)
    old_but_verified.created_at = _ago(days=400)
    await db_session.flush()

    removed = await run_cleanup(db_session)

    assert removed["unverified_users"] == 1
    remaining = {u.id for u in await _all(db_session, User)}
    assert remaining == {recent.id, old_but_verified.id}


@pytest.mark.asyncio
async def test_purging_accounts_is_itself_audited_and_takes_their_tokens_with_them(
    db_session, make_user
):
    stale = await make_user(is_verified=False)
    stale.created_at = _ago(days=30)
    db_session.add(_token(stale, expires_at=datetime.now(UTC) + timedelta(days=5)))
    await db_session.flush()

    await run_cleanup(db_session)

    assert await _all(db_session, RefreshToken) == []  # FK cascade
    entry = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "user.unverified_purged")
        )
    ).scalar_one()
    assert entry.metadata_["count"] == 1
    assert entry.actor_user_id is None


@pytest.mark.asyncio
async def test_audit_logs_are_kept_forever_unless_a_retention_is_configured(
    db_session, monkeypatch
):
    old = await record_audit_event(db_session, action="a.b", resource_type="a")
    old.created_at = _ago(days=900)
    await db_session.flush()

    monkeypatch.setattr(settings, "AUDIT_LOG_RETENTION_DAYS", None)
    removed = await run_cleanup(db_session)
    assert "audit_logs" not in removed
    assert len(await _all(db_session, AuditLog)) == 1

    monkeypatch.setattr(settings, "AUDIT_LOG_RETENTION_DAYS", 365)
    fresh = await record_audit_event(db_session, action="c.d", resource_type="c")
    removed = await run_cleanup(db_session)
    assert removed["audit_logs"] == 1
    assert [e.id for e in await _all(db_session, AuditLog)] == [fresh.id]


@pytest.mark.asyncio
async def test_running_it_twice_is_harmless(db_session, make_user):
    user = await make_user()
    db_session.add(_token(user, expires_at=_ago(days=5)))
    await db_session.flush()

    first = await run_cleanup(db_session)
    second = await run_cleanup(db_session)

    assert first["refresh_tokens"] == 1
    assert second["refresh_tokens"] == 0
