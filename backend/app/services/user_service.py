from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnauthorizedException,
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
            hashed_password=get_password_hash(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            # role/is_active/is_verified take their column defaults
            # (USER / True / False) — is_verified flips true once
            # email-verification OTP support lands (step 3).
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

        # `user.hashed_password is None` covers an OAuth-only account
        # (e.g., Google signup, step 4) trying to log in with a password it
        # never set — the same generic message as a wrong password, so this
        # doesn't leak which emails exist or how they signed up.
        if (
            user is None
            or user.hashed_password is None
            or not verify_password(password, user.hashed_password)
        ):
            raise UnauthorizedException(message="Invalid credentials")

        if not user.is_active:
            raise UnauthorizedException(message="This account has been disabled")

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
