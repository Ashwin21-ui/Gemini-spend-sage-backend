from pydantic import BaseModel, EmailStr
from uuid import UUID

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    user_id: UUID
    username: str
    email: str
    message: str
    access_token: str | None = None
    token_type: str | None = None
