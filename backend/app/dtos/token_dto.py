from uuid import UUID

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: UUID


class LoginResponse(BaseModel):
    """What POST /auth/login actually returns. `access_token`/`token_type`
    are present only when `two_factor_required` is false — a 2FA account
    doesn't get a token until /auth/2fa/verify succeeds.
    """

    two_factor_required: bool
    access_token: str | None = None
    token_type: str | None = None
