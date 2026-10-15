from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    email: EmailStr


class EmailVerifyConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class PasswordResetRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8, max_length=255)


class TwoFactorVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class TwoFactorConfirmRequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class TwoFactorDisableRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=255)
