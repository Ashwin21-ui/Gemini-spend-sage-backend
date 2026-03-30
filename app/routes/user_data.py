"""
User Data APIs - Verifies dataset thresholds cleanly restricting GUI access natively without full payload parses.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.chunk import Chunk
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
