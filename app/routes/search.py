"""
Search and Retrieval Routes
Endpoints for semantic search, filtering, and analysis of bank statements
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.db.base import SessionLocal
from app.models import Chunk, Transaction, AccountDetails, User
from app.db.vector import embed_text
from app.utils.logger import get_logger
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID

logger = get_logger(__name__)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============ Request/Response Models ============

class SearchResult(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_text: str
    date_range: str
    transaction_ids: List[int]
    transaction_amounts: List[float]
    transaction_dates: List[str]
    similarity_score: float
    previous_chunk: Optional[str] = None
    next_chunk: Optional[str] = None


class TransactionResult(BaseModel):
    id: str
    date: Optional[str]
    description: str
    amount_value: float
    amount_type: str
    reference_no: Optional[str]


class AnalysisResult(BaseModel):
    type: str
    data: dict


# ============ Semantic Search Endpoint ============

@router.post("/search-statements")
async def search_statements(
    user_id: str = Query(..., description="User UUID"),
    account_id: Optional[str] = Query(None, description="Account UUID (optional, searches all if not provided)"),
    query: str = Query(..., description="Search query (e.g., 'When did I spend 15000?')"),
    limit: int = Query(5, ge=1, le=20, description="Number of results to return"),
    db: Session = Depends(get_db)
) -> List[SearchResult]:
    """
    Semantic search across user's bank statement chunks.
    
    Embeds the user's query and finds similar transaction chunks based on embedding similarity.
    
    Args:
        user_id: UUID of the user
        account_id: Optional account UUID to filter results
        query: Search query (e.g., "When did I spend 15000?")
        limit: Number of results to return (max 20)
        db: Database session
    
    Returns:
        List of similar chunks with transaction details and chunk linking info
    """
    try:
        # Convert string UUIDs to UUID objects
        try:
            user_uuid = UUID(user_id)
            account_uuid = UUID(account_id) if account_id else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        
        # Verify user exists
        user = db.query(User).filter(User.user_id == user_uuid).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Embed the query
        query_embedding = embed_text(query)
        if not query_embedding:
            raise HTTPException(status_code=400, detail="Failed to embed query")
        
        # Build base query
        chunk_query = db.query(
            Chunk.chunk_id,
            Chunk.chunk_index,
            Chunk.chunk_text,
            Chunk.date_range,
            Chunk.transaction_ids,
            Chunk.transaction_amounts,
            Chunk.transaction_dates,
            Chunk.description_embedding,
            Chunk.previous_chunk,
            Chunk.next_chunk,
        ).filter(Chunk.user_id == user_uuid)
        
        # Filter by account if provided
        if account_uuid:
            chunk_query = chunk_query.filter(Chunk.account_id == account_uuid)
        
        chunks = chunk_query.all()
        
        if not chunks:
            return []
        
        # Calculate similarity scores (cosine similarity approximation)
        results = []
        for chunk in chunks:
            if chunk.description_embedding:
                # Simple cosine similarity (dot product of normalized vectors)
                similarity = compute_cosine_similarity(query_embedding, chunk.description_embedding)
                
                results.append({
                    'chunk_id': str(chunk.chunk_id),
                    'chunk_index': chunk.chunk_index,
                    'chunk_text': chunk.chunk_text,
                    'date_range': chunk.date_range,
                    'transaction_ids': chunk.transaction_ids,
                    'transaction_amounts': chunk.transaction_amounts,
                    'transaction_dates': chunk.transaction_dates,
                    'similarity_score': similarity,
                    'previous_chunk': str(chunk.previous_chunk) if chunk.previous_chunk else None,
                    'next_chunk': str(chunk.next_chunk) if chunk.next_chunk else None,
                })
        
        # Sort by similarity score (highest first)
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Return top results
        return results[:limit]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in search_statements: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ============ Filter Transactions Endpoint ============

@router.post("/filter-transactions")
async def filter_transactions(
    user_id: str = Query(..., description="User UUID"),
    account_id: Optional[str] = Query(None, description="Account UUID"),
    amount_min: Optional[float] = Query(None, description="Minimum transaction amount"),
    amount_max: Optional[float] = Query(None, description="Maximum transaction amount"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    amount_type: Optional[str] = Query(None, description="'credit' or 'debit'"),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db)
) -> List[TransactionResult]:
    """
    Filter transactions by amount, date, and type.
    
    Args:
        user_id: User UUID
        account_id: Optional account UUID
        amount_min: Minimum transaction amount
        amount_max: Maximum transaction amount
        date_from: Start date
        date_to: End date
        amount_type: 'credit' or 'debit'
        limit: Number of results
        db: Database session
    
    Returns:
        List of filtered transactions
    """
    try:
        # Convert string UUIDs to UUID objects
        try:
            user_uuid = UUID(user_id)
            account_uuid = UUID(account_id) if account_id else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        
        # Verify user exists
        user = db.query(User).filter(User.user_id == user_uuid).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Build query
        query = db.query(Transaction).join(
            AccountDetails, Transaction.account_id == AccountDetails.id
        ).filter(AccountDetails.user_id == user_uuid)
        
        # Apply filters
        if account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)
        
        if amount_min is not None:
            query = query.filter(Transaction.amount_value >= amount_min)
        
        if amount_max is not None:
            query = query.filter(Transaction.amount_value <= amount_max)
        
        if date_from:
            from datetime import datetime
            start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            query = query.filter(Transaction.date >= start_date)
        
        if date_to:
            from datetime import datetime
            end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            query = query.filter(Transaction.date <= end_date)
        
        if amount_type:
            query = query.filter(Transaction.amount_type == amount_type)
        
        # Execute and limit
        transactions = query.order_by(Transaction.date.desc()).limit(limit).all()
        
        return [
            TransactionResult(
                id=str(tx.id),
                date=str(tx.date) if tx.date else None,
                description=tx.description,
                amount_value=float(tx.amount_value),
                amount_type=tx.amount_type,
                reference_no=tx.reference_no
            )
            for tx in transactions
        ]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in filter_transactions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Filter failed: {str(e)}")


# ============ Analysis Endpoints ============

@router.get("/analyze-largest-transaction")
async def analyze_largest_transaction(
    user_id: str = Query(..., description="User UUID"),
    account_id: Optional[str] = Query(None, description="Account UUID"),
    db: Session = Depends(get_db)
):
    """Find the largest transaction for a user (or specific account)"""
    try:
        # Convert string UUIDs to UUID objects
        try:
            user_uuid = UUID(user_id)
            account_uuid = UUID(account_id) if account_id else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        
        user = db.query(User).filter(User.user_id == user_uuid).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        query = db.query(Transaction).join(
            AccountDetails, Transaction.account_id == AccountDetails.id
        ).filter(AccountDetails.user_id == user_uuid)
        
        if account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)
        
        largest = query.order_by(Transaction.amount_value.desc()).first()
        
        if not largest:
            return {"message": "No transactions found"}
        
        return {
            "transaction_id": str(largest.id),
            "date": str(largest.date),
            "description": largest.description,
            "amount": float(largest.amount_value),
            "type": largest.amount_type
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze_largest_transaction: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/analyze-spending-summary")
async def analyze_spending_summary(
    user_id: str = Query(..., description="User UUID"),
    account_id: Optional[str] = Query(None, description="Account UUID"),
    db: Session = Depends(get_db)
):
    """Get spending summary (total credits, debits, count)"""
    try:
        # Convert string UUIDs to UUID objects
        try:
            user_uuid = UUID(user_id)
            account_uuid = UUID(account_id) if account_id else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        
        user = db.query(User).filter(User.user_id == user_uuid).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        query = db.query(Transaction).join(
            AccountDetails, Transaction.account_id == AccountDetails.id
        ).filter(AccountDetails.user_id == user_uuid)
        
        if account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)
        
        # Credit total
        credits = query.filter(Transaction.amount_type == "credit").all()
        total_credits = sum(float(tx.amount_value) for tx in credits)
        credit_count = len(credits)
        
        # Debit total
        debits = query.filter(Transaction.amount_type == "debit").all()
        total_debits = sum(float(tx.amount_value) for tx in debits)
        debit_count = len(debits)
        
        return {
            "total_credits": total_credits,
            "credit_count": credit_count,
            "total_debits": total_debits,
            "debit_count": debit_count,
            "net_balance": total_credits - total_debits
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze_spending_summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/analyze-repeated-payments")
async def analyze_repeated_payments(
    user_id: str = Query(..., description="User UUID"),
    account_id: Optional[str] = Query(None, description="Account UUID"),
    min_repeats: int = Query(2, ge=2),
    db: Session = Depends(get_db)
):
    """Find repeated/recurring payments"""
    try:
        # Convert string UUIDs to UUID objects
        try:
            user_uuid = UUID(user_id)
            account_uuid = UUID(account_id) if account_id else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        
        user = db.query(User).filter(User.user_id == user_uuid).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        query = db.query(Transaction).join(
            AccountDetails, Transaction.account_id == AccountDetails.id
        ).filter(AccountDetails.user_id == user_uuid)
        
        if account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)
        
        transactions = query.all()
        
        # Group by description and amount
        payment_groups = {}
        for tx in transactions:
            key = (tx.description, float(tx.amount_value))
            if key not in payment_groups:
                payment_groups[key] = []
            payment_groups[key].append(tx)
        
        # Filter for repeated payments
        repeated = {
            k: v for k, v in payment_groups.items() if len(v) >= min_repeats
        }
        
        return {
            "repeated_payments": [
                {
                    "description": k[0],
                    "amount": k[1],
                    "frequency": len(v),
                    "dates": [str(tx.date) for tx in v]
                }
                for k, v in repeated.items()
            ]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze_repeated_payments: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ============ Helper Functions ============

def compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
    
    Returns:
        Cosine similarity score (0 to 1)
    """
    if not vec1 or not vec2:
        return 0.0
    
    # Compute dot product
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    
    # Compute magnitudes
    mag1 = sum(a * a for a in vec1) ** 0.5
    mag2 = sum(b * b for b in vec2) ** 0.5
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    return dot_product / (mag1 * mag2)
