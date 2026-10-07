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
        # never set — same generic message as a wrong password, so this
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

    async def get_user_by_email(self, email: str) -> User | None:
        """Unlike `get_user`, does not raise on a miss — callers that need
        to stay silent about whether an email exists (OTP request,
        password-reset request) check for `None` themselves rather than
        catching NotFoundException, so "no such user" and "DB error" can't
        get confused with each other at the call site.
        """
        return await self.repository.get_by_email(email)

    async def set_password(self, user: User, new_password: str) -> User:
        user.hashed_password = get_password_hash(new_password)
        return await self.repository.update(user)

    async def mark_verified(self, user: User) -> User:
        user.is_verified = True
        return await self.repository.update(user)

    async def set_2fa_enabled(self, user: User, *, enabled: bool) -> User:
        user.is_2fa_enabled = enabled
        return await self.repository.update(user)

    async def check_password(self, user: User, password: str) -> bool:
        """Returns a bool instead of raising — used where the caller wants
        to decide what failure means for itself (e.g. the 2FA-disable
        endpoint, which should give a normal `InvalidOTPException`-style
        400, not treat a wrong confirmation password as a full
        `authenticate_user`-style 401 login failure).
        """
        if user.hashed_password is None:
            return False
        return verify_password(password, user.hashed_password)

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

        # UserUpdateRequest.password is a plain-text field (API input
        # shape); User.hashed_password is the actual column. A blind
        # setattr loop over DTO field names would either silently no-op
        # (the column is named differently, so it'd set a stray
        # non-persisted attribute) or, worse, write an unhashed password
        # straight to the DB if the names ever matched again — handle it
        # explicitly instead of ever letting that loop touch credentials.
        password = update_data.pop("password", None)
        if password is not None:
            user.hashed_password = get_password_hash(password)

        for field, value in update_data.items():
            setattr(user, field, value)

        return await self.repository.update(user)

    async def delete_user(
        self,
        user_id: UUID,
    ) -> None:

        user = await self.get_user(user_id)

        await self.repository.delete(user)
