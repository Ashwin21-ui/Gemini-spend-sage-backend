"""Chat and ChatMessage ORM Models"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db.base import Base


class Chat(Base):
    """Chat session model - stores individual chat conversations"""
    __tablename__ = "chats"

    chat_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("account_details.id"), nullable=False, index=True)
    
    # Chat metadata
    title = Column(String, nullable=True)  # Extracted from first message (auto-generated)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    account = relationship("AccountDetails", foreign_keys=[account_id])
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan", lazy="selectin", order_by="ChatMessage.sequence_number")


class ChatMessage(Base):
    """Individual messages within a chat session"""
    __tablename__ = "chat_messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.chat_id"), nullable=False, index=True)
    
    # Message content and metadata
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Actual message text
    sources = Column(JSON, nullable=True)  # For assistant messages - sources/citations
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.now, index=True)
    sequence_number = Column(Integer, nullable=False)  # Order of messages in chat (1, 2, 3...)
    
    # Relationships
    chat = relationship("Chat", back_populates="messages", foreign_keys=[chat_id])

    def __repr__(self):
        return f"<ChatMessage {self.message_id} - {self.role}>"
