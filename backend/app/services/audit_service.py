from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dtos.audit_dto import AuditLogListResponse, AuditLogResponse
from app.repositories.audit_repository import AuditRepository


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = AuditRepository(db)

    async def list_logs(
        self,
        *,
        skip: int,
        limit: int,
        action: str | None = None,
        actor_user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> AuditLogListResponse:
        rows, total = await self.repository.search(
            skip=skip,
            limit=limit,
            action=action,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return AuditLogListResponse(
            total=total,
            items=[
                AuditLogResponse(
                    id=log.id,
                    actor_user_id=log.actor_user_id,
                    actor_email=actor_email,
                    action=log.action,
                    resource_type=log.resource_type,
                    resource_id=log.resource_id,
                    before=log.before,
                    after=log.after,
                    # The column is `metadata`; the ORM attribute is
                    # `metadata_` because `metadata` is reserved by SQLAlchemy.
                    metadata=log.metadata_,
                    request_id=log.request_id,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                    created_at=log.created_at,
                )
                for log, actor_email in rows
            ],
        )
