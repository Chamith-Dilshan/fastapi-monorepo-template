from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.config import settings
from app.dependancies.database_dep import SessionDep
from app.dependancies.rbac_dep import AdminUser, StaffUser
from app.dependancies.security_dep import CurrentUser
from app.dtos.user_dto import (
    UserListResponse,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(
    tags=["Users"],
    prefix=f"{settings.API_V1_PREFIX}/users",
)

SkipQuery = Annotated[int, Query(ge=0)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

# Who can do what (enforced here for the role gate, and in UserService for
# the "self or ..." rules that depend on *which* user is being touched):
#
#   list users ............ admin, manager
#   read a user ........... self, admin, manager
#   edit profile .......... self, admin
#   change role/status .... admin (never on yourself)
#   delete ................ admin (never yourself)


@router.get("", response_model=UserListResponse)
async def list_users(
    db: SessionDep,
    _staff: StaffUser,
    skip: SkipQuery = 0,
    limit: LimitQuery = 10,
):
    users, total = await UserService(db).list_users(skip, limit)
    return {"total": total, "items": users}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: SessionDep, current_user: CurrentUser):
    return await UserService(db).get_user_as(current_user, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    db: SessionDep,
    current_user: CurrentUser,
):
    return await UserService(db).update_user(current_user, user_id, payload)


@router.patch("/{user_id}/role", response_model=UserResponse)
async def change_user_role(
    user_id: UUID,
    payload: UserRoleUpdateRequest,
    db: SessionDep,
    admin: AdminUser,
):
    return await UserService(db).change_role(admin, user_id, payload.role)


@router.patch("/{user_id}/status", response_model=UserResponse)
async def change_user_status(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    db: SessionDep,
    admin: AdminUser,
):
    return await UserService(db).set_active(admin, user_id, is_active=payload.is_active)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, db: SessionDep, admin: AdminUser):
    await UserService(db).delete_user(admin, user_id)
