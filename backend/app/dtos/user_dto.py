from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    # Deliberately no `role` field here. Letting signup pick its own role
    # is a privilege-escalation bug waiting to happen — every self-service
    # signup gets UserRole.USER server-side (see UserService.create_user).
    # Promoting someone to admin/manager is a separate, admin-only endpoint.


class UserLoginRequest(BaseModel):
    username: EmailStr
    password: str = Field(min_length=8, max_length=255)


class UserUpdateRequest(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    is_2fa_enabled: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    total: int
    items: list[UserResponse]
