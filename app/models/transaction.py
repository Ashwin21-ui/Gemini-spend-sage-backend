"""Transaction ORM Model"""
from sqlalchemy import Column, String, Date, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db.base import Base


class Transaction(Base):
    """Transaction model for individual transactions"""
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("account_details.id"), nullable=False, index=True)
    date = Column(Date, nullable=True)
    description = Column(String)
    reference_no = Column(String)
    amount_value = Column(Numeric)
    amount_type = Column(String)  # "credit" or "debit"
    balance_after_transaction = Column(Numeric)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("AccountDetails", back_populates="transactions")
