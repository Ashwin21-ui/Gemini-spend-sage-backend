"""
Async Search Routes
Semantic search over bank statement chunks
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID
import asyncio

from app.db.base import SessionLocal
from app.db.vector import embed_text
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _search_chunks_sync(
    db: Session,
    query: str,
    account_id: UUID,
    limit: int = 5
) -> list:
    """
    Synchronous chunk search using vector similarity.
    Runs in thread pool from async context.
    """
    try:
        # Generate query embedding
        query_embedding = embed_text(query)
        
        # Convert to string format for PostgreSQL
        embedding_str = str(query_embedding)
        
        # Semantic search using pgvector similarity
        sql = text("""
            SELECT 
                chunk_text, 
                chunk_index,
                transaction_ids,
                transaction_amounts,
                transaction_dates,
                1 - (description_embedding <=> :query_embedding) as similarity
            FROM chunks
            WHERE account_id = :account_id
            ORDER BY similarity DESC
            LIMIT :limit
        """)
        
        results = db.execute(
            sql,
            {"query_embedding": embedding_str, "account_id": str(account_id), "limit": limit}
        ).fetchall()
        
        return [dict(row._mapping) for row in results]
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise


async def search_chunks_async(
    db: Session,
    query: str,
    account_id: UUID,
    limit: int = 5
) -> list:
    """Async wrapper for chunk search."""
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None,
        _search_chunks_sync,
        db,
        query,
        account_id,
        limit
    )
    return results


@router.post("/search-statements")
async def search_bank_statements(
    account_id: str = Query(..., description="UUID of the account"),
    query: str = Query(..., description="Search query"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Search bank statement chunks using semantic similarity.
    
    Args:
        account_id: Account UUID
        query: Search query string
        limit: Max results (1-20)
        db: Database session
        
    Returns:
        List of relevant chunks ordered by similarity
        
    Raises:
        HTTPException: For invalid input
    """
    try:
        # Validate account_id format
        try:
            account_uuid = UUID(account_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format for account_id: {account_id}"
            )
        
        if not query or len(query) < 3:
            raise HTTPException(
                status_code=400,
                detail="Query must be at least 3 characters"
            )
        
        logger.info(f"Searching account {account_uuid}: '{query}'")
        
        # Perform search
        results = await search_chunks_async(db, query, account_uuid, limit)
        
        if not results:
            logger.info(f"No results found for query: {query}")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "query": query,
                    "account_id": str(account_uuid),
                    "results": [],
                    "count": 0
                }
            )
        
        logger.info(f"Found {len(results)} results")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "query": query,
                "account_id": str(account_uuid),
                "results": results,
                "count": len(results)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing search"
        )
