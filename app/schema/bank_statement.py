from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

class AccountDetails(Base):
    __tablename__ = "account_details"

    id = Column(Integer, primary_key=True, index=True)
    account_holder_name = Column(String)
    account_number = Column(String)
    bank_name = Column(String)
    branch = Column(String)
    ifsc_code = Column(String)
    statement_start_date = Column(Date, nullable=True)
    statement_end_date = Column(Date, nullable=True)
    currency = Column(String)

    transactions = relationship("Transaction", back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("account_details.id"))
    date = Column(Date, nullable=True)
    description = Column(String)
    reference_no = Column(String)
    amount_value = Column(Numeric)
    amount_type = Column(String)
    balance_after_transaction = Column(Numeric)

    account = relationship("AccountDetails", back_populates="transactions")
