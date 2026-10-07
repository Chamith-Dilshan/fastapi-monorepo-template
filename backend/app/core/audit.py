"""Writes rows to the `audit_logs` table (app/models/audit_log.py).

Deliberately a plain function you call explicitly from a service, not a
middleware that fires on every request. Most requests aren't worth an
audit row (a GET, a health check); the ones that are — role changes,
deletions, and, once the VERIFIED-tag correction flow exists, every human
correction to a graph fact — should say so explicitly at the call site,
where the before/after values are actually known. Blanket middleware
can't produce a meaningful `before`/`after` without reaching back into
whatever the route just did anyway.

Usage, from a service method:

    from app.core.audit import record_audit_event

    await record_audit_event(
        db,
        actor_user_id=current_user.id,
        action="user.role_changed",
        resource_type="user",
        resource_id=str(target.id),
        before={"role": old_role.value},
        after={"role": new_role.value},
    )

Does not commit. Call it inside the same unit of work as the change it's
describing, and let that change's own commit cover both rows — an audit
row for a writing that got rolled back would be worse than no audit row.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_id
from app.models.audit_log import AuditLog


async def record_audit_event(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    actor_user_id: UUID | None = None,
    resource_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before=before,
        after=after,
        metadata_=metadata,
        request_id=get_request_id(),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    await db.flush()
    return entry
