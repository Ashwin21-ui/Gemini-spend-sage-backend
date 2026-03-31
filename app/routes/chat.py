"""
Chat API Route — GraphRAG Pipeline for Bank Statement QA + Chat Session Management
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.base import SessionLocal
from app.service.chatbot_service import chat_with_statements
from app.utils.logger import get_logger
from app.utils.dependencies import get_db, get_current_user_id, get_current_user
from app.models.user import User
from app.models.account import AccountDetails
from app.repository.chat_repo import ChatRepository
from app.schema.chat import (
    CreateChatRequest,
    SaveMessageRequest,
    SaveMessageResponse,
    ChatResponse,
    ChatListItem,
)

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
            query=request.query.strip(),
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


# ========== Chat Session Management Endpoints ==========


@router.post("/chat/sessions/new", response_model=ChatResponse)
async def create_new_chat(
    request: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session"""
    # Verify account belongs to user
    result = await db.execute(
        select(AccountDetails).where(
            (AccountDetails.id == request.account_id) & (AccountDetails.user_id == current_user.user_id)
        )
    )
    
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not found or unauthorized",
        )
    
    chat = await ChatRepository.create_chat(
        db, current_user.user_id, request.account_id
    )
    await db.commit()
    await db.refresh(chat)
    
    return ChatResponse.from_orm(chat)


@router.post("/chat/sessions/{chat_id}/message", response_model=SaveMessageResponse)
async def save_message(
    chat_id: UUID,
    request: SaveMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a message to a chat"""
    logger.info(f"[SaveMessage] Request: chat_id={chat_id}, role={request.role}, content_length={len(request.content)}")
    
    # Verify chat belongs to user
    chat = await ChatRepository.get_chat(db, chat_id, current_user.user_id)
    
    if not chat:
        logger.error(f"[SaveMessage] Chat not found: {chat_id} for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat not found or unauthorized",
        )
    
    logger.info(f"[SaveMessage] Found chat: {chat.chat_id}, existing messages: {len(chat.messages) if chat.messages else 0}")
    
    message = await ChatRepository.add_message(
        db,
        chat_id=chat_id,
        role=request.role,
        content=request.content,
        sources=request.sources,
    )
    
    logger.info(f"[SaveMessage] Saved message {message.message_id} | role={request.role} | seq={message.sequence_number}")
    
    # Update chat title if this is the first user message
    if request.role == "user" and message.sequence_number == 1:
        # Use first 50 chars of message as title
        title = request.content[:50].strip()
        if len(request.content) > 50:
            title += "..."
        await ChatRepository.update_chat_title(db, chat_id, title)
    
    await db.commit()
    
    return SaveMessageResponse(
        message_id=message.message_id,
        chat_id=message.chat_id,
        created_at=message.created_at,
        sequence_number=message.sequence_number,
    )


@router.get("/chat/sessions/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific chat with all messages"""
    logger.info(f"[GetChat] Fetching chat {chat_id} for user {current_user.user_id}")
    
    chat = await ChatRepository.get_chat(db, chat_id, current_user.user_id)
    
    if not chat:
        logger.error(f"[GetChat] Chat not found: {chat_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )
    
    msg_count = len(chat.messages) if chat.messages else 0
    logger.info(f"[GetChat] Retrieved chat {chat_id} | title={chat.title} | messages={msg_count}")
    
    return ChatResponse.from_orm(chat)


@router.get("/chat/history/list", response_model=list[ChatListItem])
async def get_chat_history(
    account_id: UUID = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for user (optionally filtered by account)"""
    history = await ChatRepository.get_chat_history(
        db, current_user.user_id, account_id
    )
    return history


@router.delete("/chat/sessions/{chat_id}")
async def delete_chat(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat"""
    success = await ChatRepository.delete_chat(db, chat_id, current_user.user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )
    
    await db.commit()
    return {"status": True, "message": "Chat deleted successfully"}

