from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.exceptions import (
    ConflictException,
    EmailNotVerifiedException,
    ForbiddenException,
    InvalidPasswordException,
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
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository

# Roles allowed to *read* other people's accounts. Writing is admin-only;
# see the individual methods.
_USER_DIRECTORY_ROLES = frozenset({UserRole.ADMIN, UserRole.MANAGER})


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
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
            # (USER / True / False) — is_verified flips true once the
            # email-verification OTP is confirmed.
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

    async def get_user_as(self, actor: User, user_id: UUID) -> User:
        """Anyone may read their own account; admins and managers may read
        anyone's. Checked before the lookup so a non-privileged caller gets
        the same 403 whether the target id exists.
        """
        if actor.id != user_id and actor.role not in _USER_DIRECTORY_ROLES:
            raise ForbiddenException(message="You do not have access to this user")
        return await self.get_user(user_id)

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User:
        user = await self.repository.get_by_email(email)

        # `user.hashed_password is None` covers an OAuth-only account
        # (e.g., Google signup) trying to log in with a password it never
        # set — the same generic message as a wrong password, so this doesn't
        # leak which emails exist or how they signed up.
        if (
            user is None
            or user.hashed_password is None
            or not verify_password(password, user.hashed_password)
        ):
            raise UnauthorizedException(message="Invalid credentials")

        if not user.is_active:
            raise UnauthorizedException(message="This account has been disabled")

        # Last, so it is only ever said to someone who knew the password.
        if not user.is_verified:
            raise EmailNotVerifiedException()

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

    async def reset_password(self, user: User, new_password: str) -> User:
        """Completing a password reset needed the one-time code
        emailed to this address, so it proves inbox ownership just as
        email verification does — the account is verified too. (It also
        quietly unsticks anyone who registered, never verified, and forgot.)
        """
        user.hashed_password = get_password_hash(new_password)
        user.is_verified = True
        return await self.repository.update(user)

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> User:
        if not await self.check_password(user, current_password):
            raise InvalidPasswordException()
        return await self.set_password(user, new_password)

    async def mark_verified(self, user: User) -> User:
        user.is_verified = True
        return await self.repository.update(user)

    async def set_2fa_enabled(self, user: User, *, enabled: bool) -> User:
        user.is_2fa_enabled = enabled
        return await self.repository.update(user)

    async def check_password(self, user: User, password: str) -> bool:
        """Returns a bool instead of raising — used where the caller wants
        to decide what failure means for itself.
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
        actor: User,
        user_id: UUID,
        payload: UserUpdateRequest,
    ) -> User:
        # Self or admin. Role, status and password are *not* editable here
        # — they have their own, stricter paths (change_role, set_active,
        # change_password) so each can carry its own rule and audit entry.
        if actor.id != user_id and actor.role != UserRole.ADMIN:
            raise ForbiddenException(message="You do not have access to this user")

        user = await self.get_user(user_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            # An explicit `null` for a NOT NULL column would be a 500 from
            # the database; "no change" is the only sensible reading.
            if value is not None:
                setattr(user, field, value)

        return await self.repository.update(user)

    async def change_role(self, actor: User, user_id: UUID, new_role: UserRole) -> User:
        # An admin demoting themselves is how a system ends up with no
        # admin at all, so it simply isn't allowed — another admin must do it.
        if actor.id == user_id:
            raise ForbiddenException(message="You cannot change your own role")

        user = await self.get_user(user_id)
        old_role = user.role
        if old_role == new_role:
            return user

        user.role = new_role
        user = await self.repository.update(user)

        await record_audit_event(
            self.db,
            action="user.role_changed",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=actor.id,
            before={"role": old_role.value},
            after={"role": new_role.value},
        )
        return user

    async def set_active(self, actor: User, user_id: UUID, *, is_active: bool) -> User:
        if actor.id == user_id:
            raise ForbiddenException(message="You cannot change your own status")

        user = await self.get_user(user_id)
        if user.is_active == is_active:
            return user

        user.is_active = is_active
        user = await self.repository.update(user)

        await record_audit_event(
            self.db,
            action="user.activated" if is_active else "user.deactivated",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=actor.id,
            before={"is_active": not is_active},
            after={"is_active": is_active},
        )
        return user

    async def delete_user(
        self,
        actor: User,
        user_id: UUID,
    ) -> None:
        if actor.id == user_id:
            raise ForbiddenException(message="You cannot delete your own account")

        user = await self.get_user(user_id)
        snapshot = {"email": user.email, "role": user.role.value}

        await self.repository.delete(user)

        await record_audit_event(
            self.db,
            action="user.deleted",
            resource_type="user",
            resource_id=str(user_id),
            actor_user_id=actor.id,
            before=snapshot,
        )
