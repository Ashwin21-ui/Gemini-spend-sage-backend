"""Chunk Pydantic Schemas"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID


class ChunkBase(BaseModel):
    """Base chunk schema"""
    chunk_text: str
    chunk_index: int
    transaction_ids: List[int]
    transaction_amounts: List[float]
    transaction_dates: List[date]
    date_range: str


class ChunkCreate(ChunkBase):
    """Schema for creating a chunk"""
    user_id: UUID
    account_id: UUID
    previous_chunk: Optional[UUID] = None
    next_chunk: Optional[UUID] = None
    description_embedding: Optional[List[float]] = None
    holder_embedding: Optional[List[float]] = None


class ChunkResponse(ChunkBase):
    """Schema for chunk response"""
    chunk_id: UUID
    user_id: UUID
    account_id: UUID
    previous_chunk: Optional[UUID] = None
    next_chunk: Optional[UUID] = None
    description_embedding: Optional[List[float]] = None
    holder_embedding: Optional[List[float]] = None
    created_at: datetime

    class Config:
        from_attributes = True
