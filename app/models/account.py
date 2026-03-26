"""AccountDetails ORM Model"""
from sqlalchemy import Column, String, Date, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db.base import Base


class AccountDetails(Base):
    """Account details model with user relationship"""
    __tablename__ = "account_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    account_holder_name = Column(String)
    account_number = Column(String)
    bank_name = Column(String)
    branch = Column(String)
    ifsc_code = Column(String)
    statement_start_date = Column(Date, nullable=True)
    statement_end_date = Column(Date, nullable=True)
    currency = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="account", cascade="all, delete-orphan")
