from typing import Annotated

from fastapi import Depends

from app.core.exceptions import NotFoundException, UnauthorizedException
from app.core.security import (
    decode_token,
    oauth2_scheme,
)
from app.dependancies.database_dep import SessionDep
from app.models.user import User
from app.services.user_service import UserService


# --- Dependency: get current user (injected into protected routes) ---
async def get_current_user_dep(
    token: Annotated[str, Depends(oauth2_scheme)], db: SessionDep
) -> User:
    # decode_token (app.core.security) already raises 401 on an invalid/
    # expired token. get_user (UserService) already raises NotFoundException
    # if the id it decoded doesn't exist. Either way this function only
    # ever returns a real User or raises — callers don't need a None check.
    service = UserService(db)
    token_data = decode_token(token)
    try:
        user = await service.get_user(token_data.user_id)
    except NotFoundException:
        # A validly signed token for an account that has since been deleted
        # is an authentication failure (401), not "resource not found" (404).
        raise UnauthorizedException(message="Could not validate credentials") from None

    # Checked on every request, not just at login: an admin deactivating an
    # account must cut off the access token that account already holds, not
    # merely stop it from logging in again. The role is likewise read fresh
    # from the database each time rather than baked into the token, so a
    # role change takes effect on the very next request.
    if not user.is_active:
        raise UnauthorizedException(message="This account has been disabled")

    return user


# Reusable alias — import this instead of redefining it per router.
CurrentUser = Annotated[User, Depends(get_current_user_dep)]
