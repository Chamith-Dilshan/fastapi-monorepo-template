from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.exceptions import InvalidOTPException, InvalidPasswordException
from app.dependancies.database_dep import SessionDep
from app.dependancies.security_dep import CurrentUser
from app.dtos.otp_dto import (
    EmailRequest,
    EmailVerifyConfirmRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    TwoFactorConfirmRequest,
    TwoFactorDisableRequest,
    TwoFactorVerifyRequest,
)
from app.dtos.token_dto import LoginResponse, RefreshRequest, Token
from app.dtos.user_dto import UserCreateRequest, UserResponse
from app.models.otp_code import OTPPurpose
from app.models.user import User
from app.services.otp_service import OTPService
from app.services.token_service import TokenService
from app.services.user_service import UserService

router = APIRouter(
    tags=["Auth"],
    prefix=f"{settings.API_V1_PREFIX}/auth",
)

# No `db.commit()` anywhere in this file, on purpose — app.core.database.get_db
# owns the transaction boundary for the whole request. See its docstring.


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: UserCreateRequest, db: SessionDep) -> User:
    """Creates the account and emails a verification code. The account
    can't log in until that code is confirmed (POST /auth/email/verify/confirm).
    """
    user = await UserService(db).create_user(payload)
    await OTPService(db).generate_and_send(user, OTPPurpose.EMAIL_VERIFICATION)
    return user


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: SessionDep,
) -> LoginResponse:
    """Exchange username and password for an access + refresh token — or,
    for an account with 2FA enabled, for a "go check your email" response
    instead. See /auth/2fa/verify for the second step in that case.
    """
    service = UserService(db)
    # authenticate_user raises UnauthorizedException (see
    # app.core.exception_handlers) on any failure — wrong password, unknown
    # email, OAuth-only account, or a disabled account — so a returned user
    # is always valid.
    user = await service.authenticate_user(form_data.username, form_data.password)

    if user.is_2fa_enabled:
        await OTPService(db).generate_and_send(user, OTPPurpose.TWO_FACTOR)
        return LoginResponse(two_factor_required=True)

    token = await TokenService(db).issue_pair(user)
    return LoginResponse(two_factor_required=False, **token.model_dump())


@router.post("/refresh", response_model=Token)
async def refresh_tokens(payload: RefreshRequest, db: SessionDep) -> Token:
    """Trade a refresh token for a fresh access + refresh pair. The old
    refresh token stops working immediately (rotation).
    """
    return await TokenService(db).refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: SessionDep) -> Response:
    """Ends this login session. Needs only the refresh token — possession
    of it is the proof — so it works even after the access token expired.
    """
    await TokenService(db).revoke(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def read_users_me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user's profile."""
    return current_user


# --- Email verification -----------------------------------------------
# Public on purpose: login is refused until the address is verified, so the
# person doing this has no token yet.


@router.post("/email/verify/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(payload: EmailRequest, db: SessionDep) -> dict:
    """(Re)sends the verification code. Answers identically for unknown
    emails, already-verified ones and disabled ones — it must not work as a
    way to find out who has an account.
    """
    user = await UserService(db).get_user_by_email(payload.email)
    if user is not None and user.is_active and not user.is_verified:
        await OTPService(db).generate_and_send(user, OTPPurpose.EMAIL_VERIFICATION)
    return {"detail": "If that account needs verifying, a code has been sent"}


@router.post("/email/verify/confirm", status_code=status.HTTP_200_OK)
async def confirm_email_verification(
    payload: EmailVerifyConfirmRequest, db: SessionDep
) -> dict:
    service = UserService(db)
    user = await service.get_user_by_email(payload.email)
    if user is None or not user.is_active:
        raise InvalidOTPException()

    await OTPService(db).verify(user, OTPPurpose.EMAIL_VERIFICATION, payload.code)
    await service.mark_verified(user)
    # No tokens here: proving the inbox is not proving the password. The
    # person signs in next, like anyone else.
    return {"detail": "Email verified"}


# --- Passwords --------------------------------------------------------


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: EmailRequest, db: SessionDep) -> dict:
    """Always returns the same response whether or not the email exists —
    this is the one piece of enumeration-safety that actually matters,
    since an attacker could otherwise use this endpoint to test whether an
    email is registered at all.
    """
    user = await UserService(db).get_user_by_email(payload.email)
    if user is not None:
        await OTPService(db).generate_and_send(user, OTPPurpose.PASSWORD_RESET)
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

    await OTPService(db).verify(user, OTPPurpose.PASSWORD_RESET, payload.code)
    await service.reset_password(user, payload.new_password)
    # Whoever knew the old password may have been the reason for the reset
    # — every existing session ends.
    await TokenService(db).revoke_all(user.id)
    return {"detail": "Password updated"}


@router.post("/password/change", response_model=Token)
async def change_password(
    payload: PasswordChangeRequest, current_user: CurrentUser, db: SessionDep
) -> Token:
    """For a logged-in user who knows their current password. Ends every
    other session and returns a fresh token pair so *this* one continues.
    """
    await UserService(db).change_password(
        current_user, payload.current_password, payload.new_password
    )
    tokens = TokenService(db)
    await tokens.revoke_all(current_user.id)
    return await tokens.issue_pair(current_user)


# --- Two-factor authentication -----------------------------------------


@router.post("/2fa/verify", response_model=Token)
async def verify_two_factor(payload: TwoFactorVerifyRequest, db: SessionDep) -> Token:
    """Step two of logging in to a 2FA-enabled account — see
    /auth/login's `two_factor_required` response.
    """
    user = await UserService(db).get_user_by_email(payload.email)
    # A deactivated account is indistinguishable from a wrong code.
    if user is None or not user.is_active:
        raise InvalidOTPException()

    await OTPService(db).verify(user, OTPPurpose.TWO_FACTOR, payload.code)
    return await TokenService(db).issue_pair(user)


@router.post("/2fa/enable/request", status_code=status.HTTP_202_ACCEPTED)
async def request_enable_two_factor(current_user: CurrentUser, db: SessionDep) -> dict:
    """Proves the account holder still controls this email address before
    2FA is turned on — reuses the TWO_FACTOR purpose rather than adding a
    fourth OTPPurpose for what is, functionally, the same check.
    """
    await OTPService(db).generate_and_send(current_user, OTPPurpose.TWO_FACTOR)
    return {"detail": "Confirmation code sent"}


@router.post("/2fa/enable/confirm", response_model=UserResponse)
async def confirm_enable_two_factor(
    payload: TwoFactorConfirmRequest, current_user: CurrentUser, db: SessionDep
) -> User:
    await OTPService(db).verify(current_user, OTPPurpose.TWO_FACTOR, payload.code)
    return await UserService(db).set_2fa_enabled(current_user, enabled=True)


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
        raise InvalidPasswordException()
    return await service.set_2fa_enabled(current_user, enabled=False)
