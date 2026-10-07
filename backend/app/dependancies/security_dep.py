from typing import Annotated

from fastapi import Depends

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
    return await service.get_user(token_data.user_id)
