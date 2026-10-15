"""Google sign-in. Two routes: /google/login redirects the browser to
Google; /google/callback is what Google redirects back to.

CSRF protection for the handshake: a random `state` value is generated,
sent to Google, and also stashed in a short-lived httpOnly cookie. On
callback, the `state` query param must match the cookie — proves the
callback request actually continues a flow *this* browser started, not
one an attacker crafted and tricked the victim into visiting. This is the
one place this template uses a cookie at all; it's scoped narrowly to the
OAuth handshake itself and unrelated to the bearer-token API auth used
everywhere else.
"""

import secrets

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.dependancies.database_dep import SessionDep
from app.dtos.token_dto import OAuthExchangeRequest, Token
from app.models.oauth_account import OAuthProvider
from app.services.oauth_service import GoogleOAuthService, OAuthService
from app.services.otp_service import OTPService
from app.services.token_service import TokenService

router = APIRouter(
    tags=["OAuth"],
    prefix=f"{settings.API_V1_PREFIX}/auth",
)

_STATE_COOKIE_NAME = "oauth_state"
_STATE_COOKIE_MAX_AGE_SECONDS = 600  # 10 minutes — generous for a login redirect


@router.get("/google/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_login() -> RedirectResponse:
    google = GoogleOAuthService()
    state = secrets.token_urlsafe(32)

    response = RedirectResponse(url=google.authorize_url(state=state))
    response.set_cookie(
        key=_STATE_COOKIE_NAME,
        value=state,
        max_age=_STATE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        # Secure cookies aren't sent over plain HTTP — only enforce this
        # outside local dev, where the app is deliberately served over
        # http://localhost.
        secure=not settings.is_local,
        samesite="lax",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: SessionDep,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    cookie_state = request.cookies.get(_STATE_COOKIE_NAME)
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise UnauthorizedException(message="Invalid or expired sign-in attempt")

    google = GoogleOAuthService()
    profile = await google.exchange_code_for_profile(code)

    oauth_service = OAuthService(db)
    user, is_new_user = await oauth_service.find_or_create_user(
        OAuthProvider.GOOGLE, profile
    )
    code = await oauth_service.complete_sign_in(user, is_new_user=is_new_user)

    # The browser lands on the frontend with a single-use, 60-second code —
    # never a token. Anything in a URL ends up in history, logs and
    # referrers; a spent code is worthless there. The frontend trades it
    # for real tokens with POST /auth/oauth/exchange.
    response = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/auth/callback?code={code}"
    )
    response.delete_cookie(_STATE_COOKIE_NAME)
    return response


@router.post("/oauth/exchange", response_model=Token)
async def exchange_oauth_code(payload: OAuthExchangeRequest, db: SessionDep) -> Token:
    user = await OTPService(db).redeem_exchange_code(payload.code)
    return await TokenService(db).issue_pair(user)
