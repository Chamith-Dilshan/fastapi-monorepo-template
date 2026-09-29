from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)
from app.dependancies.database_dep import SessionDep
from app.dependancies.security_dep import get_current_user_dep
from app.dtos.token_dto import Token
from app.dtos.user_dto import UserCreateRequest, UserResponse
from app.models.user import User
from app.services.user_service import UserService

router = APIRouter(
    tags=["Auth"],
    prefix=f"{settings.API_V1_PREFIX}/auth",
)

# Reusable alias
CurrentUser = Annotated[User, Depends(get_current_user_dep)]


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: UserCreateRequest, db: SessionDep) -> User:
    """Register a new user with a username, email, and password."""
    service = UserService(db)
    return await service.create_user(payload)


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: SessionDep,
) -> Token:
    """Exchange username and password for a JWT access token."""
    service = UserService(db)
    user = await service.authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def read_users_me(current_user: CurrentUser, db: SessionDep) -> User:
    """Return the currently authenticated user's profile."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    service = UserService(db)
    user = await service.get_user(current_user.id)
    return user
