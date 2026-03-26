"""AccountDetails Pydantic Schemas"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID
from app.schema.transaction import TransactionResponse


class AccountDetailsBase(BaseModel):
    """Base account details schema"""
    account_holder_name: str
    account_number: str
    bank_name: str
    branch: str
    ifsc_code: str
    statement_start_date: Optional[date] = None
    statement_end_date: Optional[date] = None
    currency: str


class AccountDetailsCreate(AccountDetailsBase):
    """Schema for creating account details"""
    user_id: UUID


class AccountDetailsResponse(AccountDetailsBase):
    """Schema for account details response"""
    id: UUID
    user_id: UUID
    created_at: datetime
    transactions: List[TransactionResponse] = []

    class Config:
        from_attributes = True
