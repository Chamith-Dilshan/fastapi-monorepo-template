from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.exceptions import InvalidOTPException, UnauthorizedException
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)
from app.dependancies.database_dep import SessionDep
from app.dependancies.security_dep import get_current_user_dep
from app.dtos.otp_dto import (
    OTPRequestRequest,
    PasswordResetRequest,
    TwoFactorConfirmRequest,
    TwoFactorDisableRequest,
    TwoFactorVerifyRequest,
)
from app.dtos.token_dto import LoginResponse, Token
from app.dtos.user_dto import UserCreateRequest, UserResponse
from app.models.otp_code import OTPPurpose
from app.models.user import User
from app.services.otp_service import OTPService
from app.services.user_service import UserService

router = APIRouter(
    tags=["Auth"],
    prefix=f"{settings.API_V1_PREFIX}/auth",
)

# No `db.commit()` anywhere in this file, on purpose — app.core.database.get_db
# owns the transaction boundary for the whole request. See its docstring.

# Reusable alias
CurrentUser = Annotated[User, Depends(get_current_user_dep)]


def _issue_token(user: User) -> Token:
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: UserCreateRequest, db: SessionDep) -> User:
    """Register a new user with a username, email, and password."""
    service = UserService(db)
    return await service.create_user(payload)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: SessionDep,
) -> LoginResponse:
    """Exchange username and password for a JWT access token — or, for an
    account with 2FA enabled, for a "go check your email" response
    instead. See /auth/2fa/verify for the second step in that case.
    """
    service = UserService(db)
    # authenticate_user raises UnauthorizedException (see
    # app.core.exception_handlers) on any failure — wrong password, unknown
    # email, OAuth-only account, or a disabled account — so there's no
    # `if not user` branch here; a returned user is always valid.
    user = await service.authenticate_user(form_data.username, form_data.password)

    if user.is_2fa_enabled:
        otp_service = OTPService(db)
        await otp_service.generate_and_send(user, OTPPurpose.TWO_FACTOR)
        return LoginResponse(two_factor_required=True)

    token = _issue_token(user)
    return LoginResponse(two_factor_required=False, **token.model_dump())


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def read_users_me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user's profile."""
    # CurrentUser (get_current_user_dep) already raises on any failure —
    # invalid token, or a token for a user that no longer exists — so
    # current_user here is always a real, current row. No extra DB round
    # trip needed to re-fetch what the dependency already fetched.
    return current_user


# --- Email verification -----------------------------------------------


@router.post("/email/verify/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(current_user: CurrentUser, db: SessionDep) -> dict:
    otp_service = OTPService(db)
    await otp_service.generate_and_send(current_user, OTPPurpose.EMAIL_VERIFICATION)
    return {"detail": "Verification code sent"}


@router.post("/email/verify/confirm", response_model=UserResponse)
async def confirm_email_verification(
    payload: TwoFactorConfirmRequest, current_user: CurrentUser, db: SessionDep
) -> User:
    otp_service = OTPService(db)
    await otp_service.verify(current_user, OTPPurpose.EMAIL_VERIFICATION, payload.code)
    service = UserService(db)
    user = await service.mark_verified(current_user)
    return user


# --- Password reset (no auth — this *is* how you recover account access) ----


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: OTPRequestRequest, db: SessionDep) -> dict:
    """Always returns the same response whether or not the email exists —
    this is the one piece of enumeration-safety that actually matters,
    since an attacker could otherwise use this endpoint to test whether an
    email is registered at all.
    """
    service = UserService(db)
    user = await service.get_user_by_email(payload.email)
    if user is not None:
        otp_service = OTPService(db)
        await otp_service.generate_and_send(user, OTPPurpose.PASSWORD_RESET)
    return {"detail": "If that email is registered, a reset code has been sent"}


@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def reset_password(payload: PasswordResetRequest, db: SessionDep) -> dict:
    service = UserService(db)
    user = await service.get_user_by_email(payload.email)
    if user is None:
        # Same InvalidOTPException a real user with a wrong code would
        # get — an invalid email and an invalid code look identical to the
        # caller, for the same enumeration-safety reason as the request
        # endpoint above.
        raise InvalidOTPException()

    otp_service = OTPService(db)
    await otp_service.verify(user, OTPPurpose.PASSWORD_RESET, payload.code)
    await service.set_password(user, payload.new_password)
    return {"detail": "Password updated"}


# --- Two-factor authentication -----------------------------------------


@router.post("/2fa/verify", response_model=Token)
async def verify_two_factor(payload: TwoFactorVerifyRequest, db: SessionDep) -> Token:
    """Step two of logging in to a 2FA-enabled account — see
    /auth/login's `two_factor_required` response.
    """
    service = UserService(db)
    user = await service.get_user_by_email(payload.email)
    if user is None:
        raise InvalidOTPException()

    otp_service = OTPService(db)
    await otp_service.verify(user, OTPPurpose.TWO_FACTOR, payload.code)
    return _issue_token(user)


@router.post("/2fa/enable/request", status_code=status.HTTP_202_ACCEPTED)
async def request_enable_two_factor(current_user: CurrentUser, db: SessionDep) -> dict:
    """Proves the account holder still controls this email address before
    2FA is turned on — reuses the TWO_FACTOR purpose rather than adding a
    fourth OTPPurpose for what is, functionally, the same check.
    """
    otp_service = OTPService(db)
    await otp_service.generate_and_send(current_user, OTPPurpose.TWO_FACTOR)
    return {"detail": "Confirmation code sent"}


@router.post("/2fa/enable/confirm", response_model=UserResponse)
async def confirm_enable_two_factor(
    payload: TwoFactorConfirmRequest, current_user: CurrentUser, db: SessionDep
) -> User:
    otp_service = OTPService(db)
    await otp_service.verify(current_user, OTPPurpose.TWO_FACTOR, payload.code)
    service = UserService(db)
    user = await service.set_2fa_enabled(current_user, enabled=True)
    return user


@router.post("/2fa/disable", response_model=UserResponse)
async def disable_two_factor(
    payload: TwoFactorDisableRequest, current_user: CurrentUser, db: SessionDep
) -> User:
    """Gated by the account's current password, not a fresh OTP — this is
    turning protection *off*, so it should require something the holder
    already knows, not a code sent to the same inbox the account is
    presumably still protecting.
    """
    service = UserService(db)
    if not await service.check_password(current_user, payload.password):
        raise UnauthorizedException(message="Incorrect password")

    user = await service.set_2fa_enabled(current_user, enabled=False)
    return user
