from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.security import (
    decode_token,
    oauth2_scheme,
)
from app.dependancies.database_dep import SessionDep
from app.services.user_service import UserService


# --- Dependency: get current user (injected into protected routes) ---
async def get_current_user_dep(
    token: Annotated[str, Depends(oauth2_scheme)], db: SessionDep
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    service = UserService(db)
    token_data = decode_token(token)
    user = await service.get_user(token_data.user_id)
    if user is None:
        raise credentials_exception
    return user
