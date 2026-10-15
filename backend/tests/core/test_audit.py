import pytest
from sqlalchemy import select

from app.core.audit import record_audit_event
from app.core.request_context import request_id_var
from app.models.audit_log import AuditLog


@pytest.mark.asyncio
async def test_audit_event_stores_everything_it_is_given(db_session, make_user):
    actor = await make_user()
    entry = await record_audit_event(
        db_session,
        action="thing.changed",
        resource_type="thing",
        resource_id="42",
        actor_user_id=actor.id,
        before={"a": 1},
        after={"a": 2},
        metadata={"note": "why"},
        ip_address="203.0.113.9",
        user_agent="pytest",
    )
    stored = (await db_session.execute(select(AuditLog))).scalar_one()
    assert stored.id == entry.id
    assert (stored.before, stored.after, stored.metadata_) == (
        {"a": 1},
        {"a": 2},
        {"note": "why"},
    )
    assert stored.ip_address == "203.0.113.9"


@pytest.mark.asyncio
async def test_audit_event_picks_up_the_current_request_id(db_session):
    token = request_id_var.set("req-123")
    try:
        entry = await record_audit_event(db_session, action="x.y", resource_type="x")
    finally:
        request_id_var.reset(token)
    assert entry.request_id == "req-123"


@pytest.mark.asyncio
async def test_audit_event_allows_a_system_actor(db_session):
    entry = await record_audit_event(db_session, action="job.ran", resource_type="job")
    assert entry.actor_user_id is None


@pytest.mark.asyncio
async def test_audit_rows_survive_deleting_the_actor(db_session, make_user):
    actor = await make_user()
    await record_audit_event(
        db_session, action="x.y", resource_type="x", actor_user_id=actor.id
    )
    await db_session.delete(actor)
    await db_session.flush()
    assert (
        await db_session.execute(select(AuditLog))
    ).scalar_one().actor_user_id == actor.id
