"""Pydantic schemas for Chat and ChatMessage"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ChatMessageResponse(BaseModel):
    """Schema for individual chat messages"""
    message_id: UUID
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List] = None
    created_at: datetime
    sequence_number: int

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    """Schema for chat session response"""
    chat_id: UUID
    user_id: UUID
    account_id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: Optional[List[ChatMessageResponse]] = []

    class Config:
        from_attributes = True


class ChatListItem(BaseModel):
    """Schema for chat list (used in sidebar)"""
    chat_id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int

    class Config:
        from_attributes = True


class CreateChatRequest(BaseModel):
    """Request schema for creating a new chat"""
    account_id: UUID


class SaveMessageRequest(BaseModel):
    """Request schema for saving a message to chat"""
    chat_id: UUID
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List] = None


class SaveMessageResponse(BaseModel):
    """Response schema for saved message"""
    message_id: UUID
    chat_id: UUID
    created_at: datetime
    sequence_number: int

    class Config:
        from_attributes = True
