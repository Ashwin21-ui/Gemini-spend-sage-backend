"""
Async Bank Statement Repository

Handles all database persistence for bank statements via native asyncpg mappings:
  - Account details
  - Individual transactions
  - Transaction chunks with vector embeddings
  - Chunk linked-list linking (previous_chunk / next_chunk)
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import AccountDetails, Transaction, Chunk
from app.service.chunking_service import chunk_transactions
from app.db.vector import embed_text_async
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
# Public async API natively using AsyncSession (No thread wrappers)
# ---------------------------------------------------------------------------

async def save_bank_statement(
    db: AsyncSession,
    data: Dict[str, Any],
    user_id: UUID,
) -> UUID:
    """
    Full asynchronous save:
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
    await db.flush()  # obtain account_record.id before inserting child rows

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

    await db.flush()  # obtain transaction IDs

    for i, tx_record in enumerate(transaction_records):
        chunking_data[i]["id"] = tx_record.id

    # ── 3–6. Chunks + embeddings ─────────────────────────────────────────────
    chunks = chunk_transactions(chunking_data, chunk_size=5, overlap=1)
    account_holder_name = account_data.get("account_holder_name", "")
    logger.info("Chunking complete | account=%s | chunks=%d", account_record.id, len(chunks))

    await save_chunks_with_embeddings(
        db, chunks, account_holder_name, user_id, account_record.id
    )

    # ── 7. Commit ────────────────────────────────────────────────────────────
    await db.commit()
    logger.info(
        "Statement saved | account=%s | transactions=%d | chunks=%d",
        account_record.id,
        len(transaction_records),
        len(chunks),
    )
    return account_record.id


async def save_chunks_with_embeddings(
    db: AsyncSession,
    chunks: List[Any],
    account_holder_name: str,
    user_id: UUID,
    account_id: UUID,
) -> None:
    """
    Embed each chunk, persist Chunk records, then stitch them into a linked list.
    Runs embeddings asynchronously if needed, or yields back context.
    """
    chunk_records: List[Chunk] = []

    # Note: embed_text_async connects directly to Gemini externally over async bindings natively.

    for chunk in chunks:
        try:
            desc_embedding = await embed_text_async(chunk.chunk_text)
            holder_embedding = await embed_text_async(account_holder_name)
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

    await db.flush()  # obtain chunk_id for every record

    # Link chunks into a doubly-linked list
    for i, chunk_record in enumerate(chunk_records):
        if i > 0:
            chunk_record.previous_chunk = chunk_records[i - 1].chunk_id
        if i < len(chunk_records) - 1:
            chunk_record.next_chunk = chunk_records[i + 1].chunk_id

    await db.flush()


# ---------------------------------------------------------------------------
# Pure query helpers natively async
# ---------------------------------------------------------------------------

async def get_account_by_id(
    db: AsyncSession, account_id: UUID
) -> Optional[AccountDetails]:
    result = await db.execute(select(AccountDetails).filter(AccountDetails.id == account_id))
    return result.scalars().first()


async def get_user_accounts(
    db: AsyncSession, user_id: UUID
) -> List[AccountDetails]:
    result = await db.execute(select(AccountDetails).filter(AccountDetails.user_id == user_id))
    return list(result.scalars().all())
