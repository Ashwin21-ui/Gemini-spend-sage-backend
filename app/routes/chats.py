"""Chat API routes"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.utils.dependencies import get_db, get_current_user
from app.models.user import User
from app.schema.chat import (
    CreateChatRequest,
    SaveMessageRequest,
    SaveMessageResponse,
    ChatResponse,
    ChatListItem,
)
from app.repository.chat_repo import ChatRepository
from app.models.chat import Chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/new", response_model=ChatResponse)
async def create_new_chat(
    request: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session"""
    # Verify account belongs to user
    from sqlalchemy import select
    from app.models.account import AccountDetails
    
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


@router.post("/{chat_id}/message", response_model=SaveMessageResponse)
async def save_message(
    chat_id: UUID,
    request: SaveMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a message to a chat"""
    # Verify chat belongs to user
    chat = await ChatRepository.get_chat(db, chat_id, current_user.user_id)
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat not found or unauthorized",
        )
    
    message = await ChatRepository.add_message(
        db,
        chat_id=chat_id,
        role=request.role,
        content=request.content,
        sources=request.sources,
    )
    
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


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific chat with all messages"""
    chat = await ChatRepository.get_chat(db, chat_id, current_user.user_id)
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )
    
    return ChatResponse.from_orm(chat)


@router.get("/history/list", response_model=list[ChatListItem])
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


@router.delete("/{chat_id}")
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
