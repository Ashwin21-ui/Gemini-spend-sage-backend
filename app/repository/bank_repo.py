"""
Bank Statement Repository
Handles database operations for bank statements and chunks
"""

from app.models import AccountDetails, Transaction, Chunk
from app.service.chunking_service import chunk_transactions
from app.db.vector import embed_text
from datetime import datetime
from app.utils.logger import get_logger
from typing import Dict, Any, List

logger = get_logger(__name__)


def safe_parse_date(value: str):
    """Safely parse date string to date object"""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except:
        return None


def save_bank_statement(db, data: Dict[str, Any], user_id) -> str:
    """
    Save bank statement with chunks and embeddings.
    
    Flow:
    1. Create account record
    2. Create transaction records
    3. Chunk transactions (5 + 1 overlap)
    4. Generate embeddings
    5. Save chunks with linking (previous_chunk, next_chunk)
    6. Update chunks to form a linked list
    
    Args:
        db: Database session
        data: Extracted bank statement data from Gemini
        user_id: ID (UUID) of the user uploading the statement
    
    Returns:
        account_id: UUID of the created account record
    """
    account = data["account_details"]
    
    # Create account record
    account_record = AccountDetails(
        user_id=user_id,
        account_holder_name=account.get("account_holder_name"),
        account_number=account.get("account_number"),
        bank_name=account.get("bank_name"),
        branch=account.get("branch"),
        ifsc_code=account.get("ifsc_code"),
        statement_start_date=safe_parse_date(account.get("statement_start_date")),
        statement_end_date=safe_parse_date(account.get("statement_end_date")),
        currency=account.get("currency"),
    )
    
    db.add(account_record)
    db.flush()  # Get account ID
    
    # Create transaction records and prepare data for chunking
    transaction_records = []
    transaction_data_for_chunking = []
    
    for t in data.get("transactions", []):
        transaction_record = Transaction(
            account_id=account_record.id,
            date=safe_parse_date(t.get("date")),
            description=t.get("description"),
            reference_no=t.get("reference_no"),
            amount_value=t.get("amount", {}).get("value"),
            amount_type=t.get("amount", {}).get("type"),
            balance_after_transaction=t.get("balance_after_transaction"),
        )
        db.add(transaction_record)
        transaction_records.append(transaction_record)
        
        # Prepare for chunking
        transaction_data_for_chunking.append({
            'id': None,  # Will be set after flush
            'description': t.get("description"),
            'amount_value': t.get("amount", {}).get("value"),
            'date': safe_parse_date(t.get("date")),
        })
    
    # Flush to get transaction IDs
    db.flush()
    
    # Update transaction IDs for chunking
    for i, tx_record in enumerate(transaction_records):
        transaction_data_for_chunking[i]['id'] = tx_record.id
    
    # Create chunks
    chunks = chunk_transactions(transaction_data_for_chunking, chunk_size=5, overlap=1)
    account_holder_name = account.get("account_holder_name", "")
    
    logger.info(f"Created {len(chunks)} chunks for account {account_record.id}")
    
    # Save chunks with embeddings
    _save_chunks_with_embeddings(db, chunks, account_holder_name, user_id, account_record.id)
    
    # Commit all changes
    db.commit()
    
    logger.info(f"Successfully saved account {account_record.id} with {len(chunks)} chunks")
    return account_record.id


def _save_chunks_with_embeddings(
    db,
    chunks: List[Any],
    account_holder_name: str,
    user_id,
    account_id
) -> None:
    """
    Save chunks with vector embeddings and chain linking to database.
    
    Links chunks together using previous_chunk and next_chunk fields
    for efficient sequential retrieval.
    
    Args:
        db: Database session
        chunks: List of ChunkData objects
        account_holder_name: Name of account holder
        user_id: User UUID
        account_id: Account UUID
    """
    chunk_records = []
    
    for i, chunk in enumerate(chunks):
        try:
            # Generate embeddings
            desc_embedding = embed_text(chunk.chunk_text)
            holder_embedding = embed_text(account_holder_name)
            
            # Convert transaction_ids to strings if they're UUID objects
            transaction_ids_str = [str(tid) if tid else None for tid in chunk.transaction_ids]
            transaction_dates_str = [str(d) if d else None for d in chunk.transaction_dates]
            
            # Create chunk record (without linking yet)
            chunk_record = Chunk(
                user_id=user_id,
                account_id=account_id,
                chunk_text=chunk.chunk_text,
                chunk_index=chunk.chunk_index,
                description_embedding=desc_embedding,
                holder_embedding=holder_embedding,
                transaction_ids=transaction_ids_str,
                transaction_amounts=chunk.transaction_amounts,
                transaction_dates=transaction_dates_str,
                date_range=chunk.date_range,
                previous_chunk=None,  # Will be set after flush
                next_chunk=None,      # Will be set after flush
            )
            
            db.add(chunk_record)
            chunk_records.append(chunk_record)
            logger.info(f"Created chunk {chunk.chunk_index} with {len(chunk.transaction_ids)} transactions")
            
        except Exception as e:
            logger.error(f"Error creating embeddings for chunk {chunk.chunk_index}: {str(e)}")
            # Continue saving without embeddings
            transaction_ids_str = [str(tid) if tid else None for tid in chunk.transaction_ids]
            transaction_dates_str = [str(d) if d else None for d in chunk.transaction_dates]
            
            chunk_record = Chunk(
                user_id=user_id,
                account_id=account_id,
                chunk_text=chunk.chunk_text,
                chunk_index=chunk.chunk_index,
                transaction_ids=transaction_ids_str,
                transaction_amounts=chunk.transaction_amounts,
                transaction_dates=transaction_dates_str,
                date_range=chunk.date_range,
                previous_chunk=None,
                next_chunk=None,
            )
            db.add(chunk_record)
            chunk_records.append(chunk_record)
    
    # Flush to get chunk IDs
    db.flush()
    
    # Link chunks together
    print("Linking chunks together...")
    for i, chunk_record in enumerate(chunk_records):
        # Set previous chunk
        if i > 0:
            chunk_record.previous_chunk = chunk_records[i - 1].chunk_id
        
        # Set next chunk
        if i < len(chunk_records) - 1:
            chunk_record.next_chunk = chunk_records[i + 1].chunk_id
        
        logger.info(f"Linked chunk {chunk_record.chunk_id} - prev: {chunk_record.previous_chunk}, next: {chunk_record.next_chunk}")
