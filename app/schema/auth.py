from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str
    purpose: str  # "signup" or "login"


class OTPResendRequest(BaseModel):
    email: EmailStr
    purpose: str  # "signup" or "login"


class AuthResponse(BaseModel):
    user_id: UUID
    username: str
    email: str
    message: str
    access_token: Optional[str] = None
    token_type: Optional[str] = None


class OTPSentResponse(BaseModel):
    message: str
    email: str
