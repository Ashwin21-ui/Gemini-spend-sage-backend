"""
Chunking Service: Splits transactions into overlapping chunks
Strategy: 5 transactions per chunk with 1 transaction overlap
"""

from typing import List, Dict, Any
from datetime import date
from app.utils.logger import get_logger
import json

logger = get_logger(__name__)


def format_chunk_as_json(transactions: List[Dict[str, Any]]) -> str:
    """
    Format transactions as structured JSON for better LLM understanding.
    
    Args:
        transactions: List of transaction dictionaries
    
    Returns:
        Formatted JSON string with transaction details
    """
    formatted_txs = []
    
    for idx, tx in enumerate(transactions, 1):
        formatted_tx = {
            "sequence": idx,
            "date": str(tx.get('date', 'Unknown')),
            "description": tx.get('description', ''),
            "amount": float(tx.get('amount_value', 0)),
            "type": tx.get('type', 'Unknown'),
            "balance": float(tx.get('balance_value', 0)) if tx.get('balance_value') else None,
        }
        formatted_txs.append(formatted_tx)
    
    # Create structured chunk
    chunk_data = {
        "transaction_count": len(transactions),
        "transactions": formatted_txs,
        "summary": {
            "total_amount": sum(float(tx.get('amount_value', 0)) for tx in transactions),
            "date_range": f"{transactions[0].get('date', 'Unknown')} to {transactions[-1].get('date', 'Unknown')}" if transactions else "Unknown"
        }
    }
    
    return json.dumps(chunk_data, indent=2)


class ChunkData:
    """Data class to hold chunk information"""
    def __init__(
        self,
        chunk_index: int,
        transaction_ids: List[int],
        transaction_amounts: List[float],
        transaction_dates: List[date],
        chunk_text: str,
        date_range: str
    ):
        self.chunk_index = chunk_index
        self.transaction_ids = transaction_ids
        self.transaction_amounts = transaction_amounts
        self.transaction_dates = transaction_dates
        self.chunk_text = chunk_text
        self.date_range = date_range


def chunk_transactions(
    transactions: List[Dict[str, Any]],
    chunk_size: int = 5,
    overlap: int = 1
) -> List[ChunkData]:
    """
    Create rolling window chunks of transactions.
    
    Strategy: 5 transactions per chunk with 1 overlap
    Example with 10 transactions:
        Chunk 0: [T0, T1, T2, T3, T4]
        Chunk 1: [T4, T5, T6, T7, T8]   <- T4 overlaps with previous
        Chunk 2: [T8, T9]               <- T8 overlaps with previous
    
    Args:
        transactions: List of transaction dictionaries with keys:
                     ['id', 'description', 'amount_value', 'date']
        chunk_size: Number of transactions per chunk (default: 5)
        overlap: Number of overlapping transactions (default: 1)
    
    Returns:
        List of ChunkData objects
    """
    logger.info(f"[CHUNKING_SERVICE] Starting transaction chunking...")
    logger.info(f"[CHUNKING_SERVICE] Total transactions: {len(transactions)}")
    logger.info(f"[CHUNKING_SERVICE] Chunk size: {chunk_size}, Overlap: {overlap}")
    
    if not transactions:
        logger.warning("[CHUNKING_SERVICE] No transactions to chunk!")
        return []
    
    chunks = []
    step = chunk_size - overlap  # How many new transactions per chunk
    
    i = 0
    chunk_index = 0
    
    while i < len(transactions):
        # Determine chunk boundaries
        chunk_start = i
        chunk_end = min(i + chunk_size, len(transactions))
        
        # Get transactions for this chunk
        chunk_txs = transactions[chunk_start:chunk_end]
        
        # Extract metadata from chunk transactions
        chunk_tx_ids = [tx.get('id') for tx in chunk_txs]
        chunk_amounts = [float(tx.get('amount_value', 0)) for tx in chunk_txs]
        chunk_dates = [tx.get('date') for tx in chunk_txs]
        
        # Create detailed structured chunk text with all transaction info
        chunk_text = format_chunk_as_json(chunk_txs)
        
        # Create date range string
        first_date = chunk_dates[0] if chunk_dates[0] else "Unknown"
        last_date = chunk_dates[-1] if chunk_dates[-1] else "Unknown"
        date_range = f"{first_date} to {last_date}"
        
        # Create chunk object
        chunk = ChunkData(
            chunk_index=chunk_index,
            transaction_ids=chunk_tx_ids,
            transaction_amounts=chunk_amounts,
            transaction_dates=chunk_dates,
            chunk_text=chunk_text,
            date_range=date_range
        )
        
        chunks.append(chunk)
        logger.debug(f"[CHUNKING_SERVICE] Created chunk {chunk_index}: {len(chunk_txs)} transactions, range: {date_range}")
        
        # Move to next chunk (overlapping by 'overlap' transactions)
        i += step
        chunk_index += 1
    
    logger.info(f"[CHUNKING_SERVICE] ✓ Chunking complete: {len(chunks)} chunks created")
    return chunks


def merge_chunks_with_account_data(
    chunks: List[ChunkData],
    account_holder_name: str
) -> List[Dict[str, Any]]:
    """
    Enhance chunks with account holder information for embedding.
    
    Args:
        chunks: List of ChunkData objects
        account_holder_name: Name of account holder
    
    Returns:
        List of dictionaries with chunk data ready for embedding
    """
    enhanced_chunks = []
    
    for chunk in chunks:
        enhanced_chunk = {
            'chunk_index': chunk.chunk_index,
            'chunk_text': chunk.chunk_text,
            'holder_name': account_holder_name,
            'transaction_ids': chunk.transaction_ids,
            'transaction_amounts': chunk.transaction_amounts,
            'transaction_dates': chunk.transaction_dates,
            'date_range': chunk.date_range,
            'description_to_embed': chunk.chunk_text,  # Text descriptions
            'holder_to_embed': account_holder_name,    # Account holder name
        }
        enhanced_chunks.append(enhanced_chunk)
    
    return enhanced_chunks
