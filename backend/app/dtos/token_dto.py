from uuid import UUID

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: UUID


class LoginResponse(BaseModel):
    """What POST /auth/login actually returns. The token fields are
    present only when `two_factor_required` is false — a 2FA account
    doesn't get tokens until /auth/2fa/verify succeeds.
    """

    two_factor_required: bool
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class OAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)
