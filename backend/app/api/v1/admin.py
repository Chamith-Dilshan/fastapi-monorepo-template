from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.config import settings
from app.dependancies.database_dep import SessionDep
from app.dependancies.rbac_dep import AdminUser
from app.dtos.audit_dto import AuditLogListResponse
from app.services.audit_service import AuditService

router = APIRouter(
    tags=["Admin"],
    prefix=f"{settings.API_V1_PREFIX}/admin",
)


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: SessionDep,
    _admin: AdminUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    action: Annotated[str | None, Query(max_length=150)] = None,
    actor_user_id: UUID | None = None,
    resource_type: Annotated[str | None, Query(max_length=100)] = None,
    resource_id: Annotated[str | None, Query(max_length=255)] = None,
):
    """Who did what, newest first. Admin only. Filters are exact matches and
    combine with AND.
    """
    return await AuditService(db).list_logs(
        skip=skip,
        limit=limit,
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
