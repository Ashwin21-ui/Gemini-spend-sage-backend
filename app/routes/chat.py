"""
Chat API Route — GraphRAG Pipeline for Bank Statement QA
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SessionLocal
from app.service.chatbot_service import chat_with_statements
from app.utils.logger import get_logger
from app.utils.dependencies import get_db, get_current_user_id

logger = get_logger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    account_id: str = Field(..., description="UUID of the account to query")
    query: str = Field(..., description="Natural language question")
    top_k: int = Field(5, ge=1, le=10, description="Number of chunks")

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
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
        account_uuid = UUID(request.account_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format for account_id: {request.account_id}",
        )

    if not request.query or len(request.query.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail="Query must be at least 3 characters.",
        )

    logger.info("Chat request | account=%s | query=%r | top_k=%d", account_uuid, request.query[:80], request.top_k)

    try:
        result = await chat_with_statements(
            db=db,
            user_id=current_user_id,
            account_id=account_uuid,
            query=query.strip(),
            top_k=request.top_k,
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
