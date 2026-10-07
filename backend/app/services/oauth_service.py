"""Google OAuth2 authorization-code flow, implemented directly against
Google's documented endpoints with plain httpx — no OAuth client library.
For one provider doing a standard code exchange, a library buys little
(see the note in GoogleOAuthService's docstring on why Authlib specifically
was skipped) and this is the whole flow in about 30 lines.

Adding a second provider later: this class's three methods
(authorize_url / exchange_code_for_profile / the Profile shape) are the
seam. A new provider implements the same three things against its own
endpoints; `OAuthService.find_or_create_user` below doesn't change at all,
since it only ever sees the normalized `OAuthProfile`.
"""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.security import create_access_token
from app.dtos.token_dto import Token
from app.models.oauth_account import OAuthProvider
from app.models.user import User
from app.repositories.oauth_repository import OAuthRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class OAuthProfile:
    provider_account_id: str
    email: str
    email_verified: bool
    first_name: str
    last_name: str


class GoogleOAuthService:
    """Talks to Google only. Knows nothing about our User model — that's
    OAuthService's job below. Kept separate so "how do we talk to Google"
    and "what do we do with the result" can change independently, and so a
    second provider doesn't mean editing this class.

    Authlib was deliberately not used here even though it's the common
    choice for this: Authlib 1.8's HTTP client wrapper emits a deprecation
    warning pointing at `httpx2` (a separate package, not installed), and
    there are reports of Authlib 1.8 + httpx2-installed combinations
    actually crashing on timeout handling. For one provider doing a
    textbook authorization-code exchange, that's a dependency and a known
    rough edge bought for very little — plain httpx against Google's
    documented endpoints is both simpler and more stable right now.
    """

    def __init__(self) -> None:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise RuntimeError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set to use Google sign-in."
            )

    def authorize_url(self, *, state: str) -> str:
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        query = httpx.QueryParams(params)
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    async def exchange_code_for_profile(self, code: str) -> OAuthProfile:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise UnauthorizedException(message="Google sign-in failed")
            access_token = token_response.json().get("access_token")

            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code != 200:
                raise UnauthorizedException(message="Google sign-in failed")
            info = userinfo_response.json()

        return OAuthProfile(
            provider_account_id=info["sub"],
            email=info["email"],
            email_verified=info.get("email_verified", False),
            first_name=info.get("given_name", ""),
            last_name=info.get("family_name", ""),
        )


class OAuthService:
    """Provider-agnostic: given a normalized `OAuthProfile`, finds or
    creates the User and OAuthAccount rows and issues our own JWT. Nothing
    here is Google-specific.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.oauth_repository = OAuthRepository(db)
        self.user_repository = UserRepository(db)

    async def find_or_create_user(
        self, provider: OAuthProvider, profile: OAuthProfile
    ) -> tuple[User, bool]:
        """Returns (user, is_new_user)."""
        existing_link = await self.oauth_repository.get_by_provider_account(
            provider, profile.provider_account_id
        )
        if existing_link is not None:
            user = await self.user_repository.get_by_id(existing_link.user_id)
            # oauth_accounts.user_id is a FK with ON DELETE CASCADE (see
            # app/models/oauth_account.py) — this row existing guarantees
            # the user row does too. Asserted rather than silently typed
            # as User | None, so a future change to that constraint fails
            # loudly here instead of producing a confusing None downstream.
            assert user is not None, (
                "OAuthAccount referenced a user that no longer exists"
            )
            return user, False

        # No link yet. If a user with this email already exists (they
        # signed up with a password first), link this provider onto that
        # account rather than creating a duplicate — same person, two ways
        # in. Otherwise, create a brand-new account.
        user = await self.user_repository.get_by_email(profile.email)
        is_new_user = user is None
        if user is None:
            user = User(
                email=profile.email,
                hashed_password=None,
                first_name=profile.first_name or profile.email.split("@")[0],
                last_name=profile.last_name or "",
                # Google already verified this address; no reason to make
                # the user prove it to us again via our own OTP flow.
                is_verified=profile.email_verified,
            )
            user = await self.user_repository.create(user)

        await self.oauth_repository.create(
            user.id, provider, profile.provider_account_id
        )
        # No commit here — app.core.database.get_db commits once for the
        # whole request. Both the user creation above and this link land
        # together when the /auth/google/callback route returns.
        return user, is_new_user

    async def issue_token_and_welcome(self, user: User, *, is_new_user: bool) -> Token:
        if is_new_user:
            try:
                await EmailService().send_welcome_email(
                    to=user.email, first_name=user.first_name
                )
            except Exception:
                # Same reasoning as otp_service: a failed welcome email is
                # not a failed sign-in.
                pass

        access_token = create_access_token(data={"sub": str(user.id)})
        return Token(access_token=access_token, token_type="bearer")
