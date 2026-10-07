from pydantic import BaseModel, EmailStr, Field

from app.models.otp_code import OTPPurpose


class OTPRequestRequest(BaseModel):
    email: EmailStr
    purpose: OTPPurpose


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    purpose: OTPPurpose
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
