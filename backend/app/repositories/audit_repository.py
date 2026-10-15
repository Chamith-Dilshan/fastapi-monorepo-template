from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.models.audit_log import AuditLog
from app.models.user import User


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        *,
        skip: int,
        limit: int,
        action: str | None = None,
        actor_user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> tuple[list[tuple[AuditLog, str | None]], int]:
        """Newest first. Each row comes with the actor's *current* email (an
        outer join: system actions and deleted actors have none)."""
        filters = []
        if action:
            filters.append(AuditLog.action == action)
        if actor_user_id:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            filters.append(AuditLog.resource_id == resource_id)

        try:
            total = await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(*filters)
            )
            result = await self.db.execute(
                select(AuditLog, User.email)
                .join(User, User.id == AuditLog.actor_user_id, isouter=True)
                .where(*filters)
                # id as the tiebreaker: stable pages when timestamps collide.
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset(skip)
                .limit(limit)
            )
            return [(row[0], row[1]) for row in result.all()], total or 0
        except SQLAlchemyError as exc:
            raise DatabaseException() from exc
