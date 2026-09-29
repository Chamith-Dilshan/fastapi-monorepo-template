from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.core.security import (
    get_password_hash,
    verify_password,
)
from app.dtos.user_dto import (
    UserCreateRequest,
    UserUpdateRequest,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, db: AsyncSession):
        self.repository = UserRepository(db)

    async def create_user(
        self,
        payload: UserCreateRequest,
    ) -> User:

        existing_user = await self.repository.get_by_email(payload.email)

        if existing_user:
            raise ConflictException(
                message="Email already exists",
                status_code=409,
            )

        user = User(
            email=payload.email,
            password=get_password_hash(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
        )

        new_user = await self.repository.create(user)
        return new_user

    async def get_user(
        self,
        user_id: UUID,
    ) -> User:

        user = await self.repository.get_by_id(user_id)

        if not user:
            raise NotFoundException(
                message="User not found",
                status_code=404,
            )

        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User | None:
        user = await self.repository.get_by_email(email)

        if user is None or not verify_password(
            password,
            user.password,
        ):
            raise HTTPException(
                detail="Invalid credentials",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return user

    async def list_users(
        self,
        skip: int,
        limit: int,
    ) -> tuple[list[User], int]:
        return await self.repository.get_all(
            skip=skip,
            limit=limit,
        )

    async def update_user(
        self,
        user_id: UUID,
        payload: UserUpdateRequest,
    ) -> User:

        user = await self.get_user(user_id)

        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(user, field, value)

        return await self.repository.update(user)

    async def delete_user(
        self,
        user_id: UUID,
    ) -> None:

        user = await self.get_user(user_id)

        await self.repository.delete(user)
