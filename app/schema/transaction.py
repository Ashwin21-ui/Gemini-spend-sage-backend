"""Transaction Pydantic Schemas"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional
from uuid import UUID


class TransactionBase(BaseModel):
    """Base transaction schema"""
    date: Optional[date] = None
    description: str
    reference_no: Optional[str] = None
    amount_value: float
    amount_type: str  # "credit" or "debit"
    balance_after_transaction: Optional[float] = None


class TransactionCreate(TransactionBase):
    """Schema for creating a transaction"""
    account_id: UUID


class TransactionResponse(TransactionBase):
    """Schema for transaction response"""
    id: UUID
    account_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
