from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    # Looked up at read time. None for system actions, and for actors whose
    # account has since been deleted (the row itself deliberately outlives
    # them — see app/models/audit_log.py).
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    before: dict | None
    after: dict | None
    metadata: dict | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogResponse]
