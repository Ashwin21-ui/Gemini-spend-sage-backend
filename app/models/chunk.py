"""Chunk ORM Model - stores transaction chunks with embeddings"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid
from app.db.base import Base


class Chunk(Base):
    """Chunk model for storing transaction chunks with vector embeddings"""
    __tablename__ = "chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("account_details.id"), nullable=False, index=True)
    
    # Chunk linking for sequential retrieval
    previous_chunk = Column(UUID(as_uuid=True), ForeignKey("chunks.chunk_id"), nullable=True, index=True)
    next_chunk = Column(UUID(as_uuid=True), ForeignKey("chunks.chunk_id"), nullable=True, index=True)
    
    # Content
    chunk_text = Column(Text, nullable=False)  # Combined transaction descriptions
    chunk_index = Column(Integer, nullable=False)  # Sequential index within statement
    
    # Embeddings (3072 dimensions for gemini-embedding-001)
    description_embedding = Column(Vector(3072), nullable=True)  # For transaction descriptions
    holder_embedding = Column(Vector(3072), nullable=True)  # For account holder name
    
    # Metadata for analysis
    transaction_ids = Column(JSON, nullable=True)  # Array of transaction IDs
    transaction_amounts = Column(JSON, nullable=True)  # Array of amounts
    transaction_dates = Column(JSON, nullable=True)  # Array of dates
    date_range = Column(String, nullable=True)  # e.g., "2024-01-01 to 2024-01-05"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="chunks")
    account = relationship("AccountDetails", back_populates="chunks")
