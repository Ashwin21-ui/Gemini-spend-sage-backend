"""User Pydantic Schemas"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID


class UserBase(BaseModel):
    """Base user schema"""
    username: Optional[str] = None
    email: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a user"""
    pass


class UserResponse(UserBase):
    """Schema for user response"""
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
