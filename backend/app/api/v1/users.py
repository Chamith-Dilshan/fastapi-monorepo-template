from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.config import settings
from app.dependancies.database_dep import SessionDep
from app.dependancies.security_dep import get_current_user_dep
from app.dtos.user_dto import (
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.models.user import User
from app.services.user_service import UserService

router = APIRouter(
    tags=["Users"],
    prefix=f"{settings.API_V1_PREFIX}/users",
)

SkipQuery = Annotated[int, Query(ge=0)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

# Reusable alias
CurrentUser = Annotated[User, Depends(get_current_user_dep)]

# NOTE: every route below requires *a* valid logged-in user (via
# CurrentUser), but not yet a specific role — any authenticated user can
# currently list/view/edit/delete any other user by id. That's a real gap,
# not just unused-argument noise: once `core/rbac.py` and
# `require_role()` land (ground-template plan, step 5), these should
# become `require_role(UserRole.ADMIN)` instead of a bare `CurrentUser`.
# The leading underscore below is only there to tell Ruff the parameter
# is deliberately unused for now, not a statement that auth is unused.


@router.get(
    "",
    response_model=UserListResponse,
)
async def list_users(
    db: SessionDep,
    _current_user: CurrentUser,
    skip: SkipQuery = 0,
    limit: LimitQuery = 10,
):
    service = UserService(db)

    users, total = await service.list_users(
        skip,
        limit,
    )

    return {
        "total": total,
        "items": users,
    }


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
async def get_user(user_id: UUID, db: SessionDep, _current_user: CurrentUser):
    service = UserService(db)

    return await service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    db: SessionDep,
    _current_user: CurrentUser,
):
    service = UserService(db)

    return await service.update_user(
        user_id,
        payload,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(user_id: UUID, db: SessionDep, _current_user: CurrentUser):
    service = UserService(db)

    await service.delete_user(user_id)
