"""Chat repository for database operations"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from uuid import UUID
from app.models.chat import Chat, ChatMessage
from app.schema.chat import ChatListItem


class ChatRepository:
    """Repository class for chat operations"""

    @staticmethod
    async def create_chat(session: AsyncSession, user_id: UUID, account_id: UUID, title: str = None) -> Chat:
        """Create a new chat session"""
        chat = Chat(user_id=user_id, account_id=account_id, title=title)
        session.add(chat)
        await session.flush()
        return chat

    @staticmethod
    async def add_message(
        session: AsyncSession,
        chat_id: UUID,
        role: str,
        content: str,
        sources: list = None,
    ) -> ChatMessage:
        """Add a message to a chat"""
        # Get the next sequence number
        result = await session.execute(
            select(func.max(ChatMessage.sequence_number)).where(ChatMessage.chat_id == chat_id)
        )
        max_seq = result.scalar() or 0
        
        message = ChatMessage(
            chat_id=chat_id,
            role=role,
            content=content,
            sources=sources,
            sequence_number=max_seq + 1,
        )
        session.add(message)
        await session.flush()
        return message

    @staticmethod
    async def update_chat_title(session: AsyncSession, chat_id: UUID, title: str) -> Chat:
        """Update chat title (usually from first user message)"""
        result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
        chat = result.scalar_one_or_none()
        if chat:
            chat.title = title
            await session.flush()
        return chat

    @staticmethod
    async def get_chat(session: AsyncSession, chat_id: UUID, user_id: UUID) -> Chat:
        """Get a specific chat with all messages"""
        from sqlalchemy import select
        
        result = await session.execute(
            select(Chat)
            .where(and_(Chat.chat_id == chat_id, Chat.user_id == user_id))
        )
        chat = result.scalar_one_or_none()
        
        return chat

    @staticmethod
    async def get_chat_history(session: AsyncSession, user_id: UUID, account_id: UUID = None) -> list[ChatListItem]:
        """Get chat history for a user (with optional account filter)"""
        query = select(
            Chat.chat_id,
            Chat.title,
            Chat.created_at,
            Chat.updated_at,
            func.count(ChatMessage.message_id).label("message_count"),
        ).where(Chat.user_id == user_id)
        
        if account_id:
            query = query.where(Chat.account_id == account_id)
        
        query = query.outerjoin(ChatMessage).group_by(Chat.chat_id).order_by(desc(Chat.created_at))
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        return [
            ChatListItem(
                chat_id=row.chat_id,
                title=row.title or f"Chat {row.created_at.strftime('%b %d, %H:%M')}",
                created_at=row.created_at,
                updated_at=row.updated_at,
                message_count=row.message_count or 0,
            )
            for row in rows
        ]

    @staticmethod
    async def delete_chat(session: AsyncSession, chat_id: UUID, user_id: UUID) -> bool:
        """Delete a chat and all its messages"""
        result = await session.execute(
            select(Chat).where(and_(Chat.chat_id == chat_id, Chat.user_id == user_id))
        )
        chat = result.scalar_one_or_none()
        if chat:
            await session.delete(chat)
            await session.flush()
            return True
        return False
