from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class AuditLog(Base):
    """An immutable record of a sensitive or reviewable action.

    Not every request is audited here — access/timing logging is the job of
    `app.core.middleware.RequestContextMiddleware`. This table is for
    actions worth being able to answer "who did this, when, and what changed"
    for later: role/permission changes, deletions, and — once the workspace
    overlay and `VERIFIED`-tag correction flow exist (`PROJECT_BIBLE.md`
    Section 5, `BACKEND_DEVELOPMENT_PLAN.md` Section 3) — every human
    correction to a graph fact. `before`/`after` already matches that
    corrections-version-never-overwrite shape, so this table doesn't need to
    change shape when that flow lands; it just starts getting called from
    more places.

    Rows are written, never updated or deleted, by
    `app.core.audit.record_audit_event`.
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Nullable: some audited actions (a failed login, a system job) have no
    # authenticated actor.
    actor_user_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)

    # A short, stable slug — e.g. "user.role_changed", "post.deleted",
    # "fact.corrected". Not a free-text description; that's `metadata_`.
    action: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Free-form context that doesn't fit before/after — e.g., a reviewer's
    # note, or which workspace raised a queue entry once workspaces exist.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    request_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
