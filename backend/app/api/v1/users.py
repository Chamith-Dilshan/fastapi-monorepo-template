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


@router.get(
    "",
    response_model=UserListResponse,
)
async def list_users(
    db: SessionDep,
    current_user: CurrentUser,
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
async def get_user(user_id: UUID, db: SessionDep, current_user: CurrentUser):
    service = UserService(db)

    return await service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID, payload: UserUpdateRequest, db: SessionDep, current_user: CurrentUser
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
async def delete_user(user_id: UUID, db: SessionDep, current_user: CurrentUser):
    service = UserService(db)

    await service.delete_user(user_id)
