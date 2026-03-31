"""
User Data APIs - Verifies dataset thresholds cleanly restricting GUI access natively without full payload parses.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.chunk import Chunk
from app.models.account import AccountDetails
from app.models.transaction import Transaction
from app.utils.dependencies import get_db, get_current_user_id
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.get("/user-data/check")
async def check_user_data(
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Checks if a user has any chunks generated natively restricting skip buttons mapping directly into Chat environments safely.
    Returns 404 cleanly triggering frontend routing blockages natively.
    """
    try:
        query = select(Chunk.account_id).where(Chunk.user_id == current_user_id).limit(1)
        result = await db.execute(query)
        account_id = result.scalar_one_or_none()

        if account_id is None:
            logger.warning(f"Data lookup triggered 404 isolation fault gracefully | user={current_user_id}")
            raise HTTPException(status_code=404, detail="No data found. Upload a bank statement first.")
            
        return {"has_data": True, "latest_account_id": str(account_id)}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Failed resolving user mapping checks: {e}")
        raise HTTPException(status_code=500, detail="Failed checking user data.")


@router.get("/user-data/accounts")
async def get_user_accounts(
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Get all uploaded bank statements (accounts) for the current user.
    Used by sidebar to display list of statements.
    """
    try:
        query = select(AccountDetails).where(AccountDetails.user_id == current_user_id)
        result = await db.execute(query)
        accounts = result.scalars().all()

        return {
            "accounts": [
                {
                    "id": str(account.id),
                    "account_holder_name": account.account_holder_name,
                    "account_number": account.account_number,
                    "bank_name": account.bank_name,
                    "statement_start_date": account.statement_start_date.isoformat() if account.statement_start_date else None,
                    "statement_end_date": account.statement_end_date.isoformat() if account.statement_end_date else None,
                    "currency": account.currency or "INR",
                }
                for account in accounts
            ]
        }
    except Exception as e:
        logger.error(f"Failed fetching user accounts: {e}")
        raise HTTPException(status_code=500, detail="Failed fetching accounts.")


@router.get("/user-data/transactions/{account_id}")
async def get_account_transactions(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Get all transactions for a specific account.
    Used by statements view to display transaction data.
    """
    try:
        # Verify the account belongs to the current user
        account_query = select(AccountDetails).where(
            AccountDetails.id == account_id,
            AccountDetails.user_id == current_user_id
        )
        account_result = await db.execute(account_query)
        account = account_result.scalar_one_or_none()
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Fetch transactions for this account
        transactions_query = select(Transaction).where(
            Transaction.account_id == account_id
        ).order_by(Transaction.date.desc())
        
        result = await db.execute(transactions_query)
        transactions = result.scalars().all()
        
        return {
            "account_id": str(account_id),
            "currency": account.currency or "INR",
            "transactions": [
                {
                    "id": str(txn.id),
                    "date": txn.date.isoformat() if txn.date else None,
                    "description": txn.description,
                    "reference_no": txn.reference_no,
                    "amount": float(txn.amount_value) if txn.amount_value else None,
                    "type": txn.amount_type,
                    "balance": float(txn.balance_after_transaction) if txn.balance_after_transaction else None,
                }
                for txn in transactions
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed fetching transactions for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed fetching transactions.")
