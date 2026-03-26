"""
Async Bank Statement Repository

Handles all database persistence for bank statements:
  - Account details
  - Individual transactions
  - Transaction chunks with vector embeddings
  - Chunk linked-list linking (previous_chunk / next_chunk)

Architecture note:
  SQLAlchemy's Session is NOT thread-safe, but it IS safe to run a single
  session's operations in a dedicated thread via asyncio.to_thread() /
  run_in_executor — which is exactly what we do here.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AccountDetails, Transaction, Chunk
from app.service.chunking_service import chunk_transactions
from app.db.vector import embed_text
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def safe_parse_date(value: Optional[str]):
    """
    Parse an ISO date string (YYYY-MM-DD) to a date object.
    Returns None silently on any parse failure — no hard crash on dirty data.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def save_bank_statement_async(
    db: Session,
    data: Dict[str, Any],
    user_id: UUID,
) -> UUID:
    """
    Persist a fully extracted bank statement to the database.

    Runs all synchronous DB operations in a thread pool so the event loop
    remains unblocked.

    Args:
        db:      Active SQLAlchemy session.
        data:    Extracted bank statement dict (from Gemini).
        user_id: UUID of the uploading user.

    Returns:
        UUID of the newly created AccountDetails record.
    """
    loop = asyncio.get_running_loop()
    account_id = await loop.run_in_executor(
        None, _save_bank_statement_sync, db, data, user_id
    )
    return account_id


async def get_account_by_id_async(
    db: Session, account_id: UUID
) -> Optional[AccountDetails]:
    """Async wrapper — fetch a single account by its UUID."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _get_account_by_id_sync, db, account_id
    )


async def get_user_accounts_async(
    db: Session, user_id: UUID
) -> List[AccountDetails]:
    """Async wrapper — fetch all accounts belonging to a user."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _get_user_accounts_sync, db, user_id
    )


# ---------------------------------------------------------------------------
# Synchronous DB workers (called via run_in_executor)
# ---------------------------------------------------------------------------

def _save_bank_statement_sync(
    db: Session, data: Dict[str, Any], user_id: UUID
) -> UUID:
    """
    Full synchronous save:
      1. Create AccountDetails record
      2. Create Transaction records
      3. Chunk transactions (size=5, overlap=1)
      4. Generate vector embeddings per chunk
      5. Save Chunk records
      6. Link chunks into a doubly-linked list (prev/next)
      7. Commit
    """
    account_data = data["account_details"]

    # ── 1. Account ───────────────────────────────────────────────────────────
    account_record = AccountDetails(
        user_id=user_id,
        account_holder_name=account_data.get("account_holder_name"),
        account_number=account_data.get("account_number"),
        bank_name=account_data.get("bank_name"),
        branch=account_data.get("branch"),
        ifsc_code=account_data.get("ifsc_code"),
        statement_start_date=safe_parse_date(account_data.get("statement_start_date")),
        statement_end_date=safe_parse_date(account_data.get("statement_end_date")),
        currency=account_data.get("currency"),
    )
    db.add(account_record)
    db.flush()  # obtain account_record.id before inserting child rows

    # ── 2. Transactions ──────────────────────────────────────────────────────
    transaction_records: List[Transaction] = []
    chunking_data: List[Dict[str, Any]] = []

    for t in data.get("transactions", []):
        tx = Transaction(
            account_id=account_record.id,
            date=safe_parse_date(t.get("date")),
            description=t.get("description"),
            reference_no=t.get("reference_no"),
            amount_value=t.get("amount", {}).get("value"),
            amount_type=t.get("amount", {}).get("type"),
            balance_after_transaction=t.get("balance_after_transaction"),
        )
        db.add(tx)
        transaction_records.append(tx)
        chunking_data.append({
            "id": None,  # filled after flush
            "description": t.get("description"),
            "amount_value": t.get("amount", {}).get("value"),
            "date": safe_parse_date(t.get("date")),
        })

    db.flush()  # obtain transaction IDs

    for i, tx_record in enumerate(transaction_records):
        chunking_data[i]["id"] = tx_record.id

    # ── 3–6. Chunks + embeddings ─────────────────────────────────────────────
    chunks = chunk_transactions(chunking_data, chunk_size=5, overlap=1)
    account_holder_name = account_data.get("account_holder_name", "")
    logger.info("Chunking complete | account=%s | chunks=%d", account_record.id, len(chunks))

    _save_chunks_with_embeddings(
        db, chunks, account_holder_name, user_id, account_record.id
    )

    # ── 7. Commit ────────────────────────────────────────────────────────────
    db.commit()
    logger.info(
        "Statement saved | account=%s | transactions=%d | chunks=%d",
        account_record.id,
        len(transaction_records),
        len(chunks),
    )
    return account_record.id


def _save_chunks_with_embeddings(
    db: Session,
    chunks: List[Any],
    account_holder_name: str,
    user_id: UUID,
    account_id: UUID,
) -> None:
    """
    Embed each chunk, persist Chunk records, then stitch them into a linked list.
    """
    chunk_records: List[Chunk] = []

    for chunk in chunks:
        try:
            desc_embedding = embed_text(chunk.chunk_text)
            holder_embedding = embed_text(account_holder_name)
        except Exception as exc:
            logger.error(
                "Embedding failed for chunk %d — saving without embeddings | error=%s",
                chunk.chunk_index, exc,
            )
            desc_embedding = None
            holder_embedding = None

        transaction_ids_str = [str(tid) if tid else None for tid in chunk.transaction_ids]
        transaction_dates_str = [str(d) if d else None for d in chunk.transaction_dates]

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
            previous_chunk=None,
            next_chunk=None,
        )
        db.add(chunk_record)
        chunk_records.append(chunk_record)

    db.flush()  # obtain chunk_id for every record

    # Link chunks into a doubly-linked list
    for i, chunk_record in enumerate(chunk_records):
        if i > 0:
            chunk_record.previous_chunk = chunk_records[i - 1].chunk_id
        if i < len(chunk_records) - 1:
            chunk_record.next_chunk = chunk_records[i + 1].chunk_id

    db.flush()


# ---------------------------------------------------------------------------
# Pure query helpers (thin wrappers around SQLAlchemy queries)
# ---------------------------------------------------------------------------

def _get_account_by_id_sync(
    db: Session, account_id: UUID
) -> Optional[AccountDetails]:
    return db.query(AccountDetails).filter(AccountDetails.id == account_id).first()


def _get_user_accounts_sync(
    db: Session, user_id: UUID
) -> List[AccountDetails]:
    return db.query(AccountDetails).filter(AccountDetails.user_id == user_id).all()
