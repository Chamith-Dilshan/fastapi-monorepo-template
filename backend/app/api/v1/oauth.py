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
from app.models.oauth_account import OAuthProvider
from app.services.oauth_service import GoogleOAuthService, OAuthService

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
    user, is_new_user = await oauth_service.find_or_create_user(OAuthProvider.GOOGLE, profile)
    token = await oauth_service.issue_token_and_welcome(user, is_new_user=is_new_user)

    # Bearer-token SPA, no server-side session — the token has to reach
    # the frontend somehow, and a query param on a redirect is the
    # standard way to do that without a shared cookie domain. Trade-off,
    # on purpose: it's one step less secure than a one-time exchange code
    # (the token can end up in browser history / a referrer header), but
    # keeps this template's OAuth flow to two routes instead of three.
    # Swap this for a short-lived exchange code if that trade-off doesn't
    # fit a given deployment.
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?access_token={token.access_token}"
    response = RedirectResponse(url=redirect_url)
    response.delete_cookie(_STATE_COOKIE_NAME)
    return response
