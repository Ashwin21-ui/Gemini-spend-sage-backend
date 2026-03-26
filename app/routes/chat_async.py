"""
Chat API Route — GraphRAG Pipeline for Bank Statement QA
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.service.chatbot_service import chat_with_statements
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/chat")
async def chat_endpoint(
    account_id: str = Query(..., description="UUID of the account to query against"),
    query: str = Query(..., description="Natural language question about the bank statement"),
    top_k: int = Query(5, ge=1, le=10, description="Number of top chunks for context (1–10)"),
    db: Session = Depends(get_db),
):
    """
    GraphRAG chat endpoint — ask natural language questions about a bank statement.

    Pipeline: guardrails → embed → dual search → rerank → graph expand → LLM answer.

    Args:
        account_id: Account UUID to scope the search.
        query:      Natural language question (e.g. "What are my largest debits?").
        top_k:      How many top chunks to retrieve for context.
        db:         Database session.

    Returns:
        JSON with the LLM-generated answer, sources, and pipeline metadata.
    """
    # Validate account_id
    try:
        account_uuid = UUID(account_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format for account_id: {account_id}",
        )

    if not query or len(query.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail="Query must be at least 3 characters.",
        )

    logger.info("Chat request | account=%s | query=%r | top_k=%d", account_uuid, query[:80], top_k)

    try:
        result = await chat_with_statements(
            db=db,
            account_id=account_uuid,
            query=query.strip(),
            top_k=top_k,
        )
    except Exception as exc:
        logger.error("Chat pipeline failed | error=%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Chat processing failed.")

    return JSONResponse(
        status_code=200,
        content={
            "answer": result.answer,
            "query": result.query,
            "account_id": result.account_id,
            "guardrail": {
                "passed": result.guardrail_passed,
                "category": result.guardrail_category,
            },
            "sources": result.sources,
            "chunks_used": result.chunks_used,
            "pipeline": result.pipeline_steps,
        },
    )
