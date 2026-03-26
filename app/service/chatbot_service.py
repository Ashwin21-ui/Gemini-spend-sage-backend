"""
Chatbot Service — GraphRAG Pipeline for Bank Statement QA

Pipeline:
  Query
    │
    ▼
  1. Guardrails          → Gemini classifies query as finance-relevant or off-topic.
    │                       Rejects off-topic / unsafe queries immediately.
    ▼
  2. Query Embedding     → embed_query() with retrieval_query task type.
    │
    ▼
  3. Dual Search         → Runs in PARALLEL:
    │  ├─ Semantic search  pgvector cosine similarity (top-10)
    │  └─ Keyword search   PostgreSQL ILIKE on chunk_text + transaction descriptions (top-10)
    ▼
  4. Merge & Deduplicate → Union of both result sets, keyed by chunk_id.
    │
    ▼
  5. Re-rank             → Weighted score: 0.65 × semantic + 0.35 × keyword_hit_ratio
    │                       Take top-K.
    ▼
  6. Graph Expansion     → For each top-K chunk, fetch prev_chunk and next_chunk
    │                       neighbours from the linked-list structure. Adds surrounding
    │                       context without re-ranking (neighbours are context, not hits).
    ▼
  7. LLM Answer          → Gemini 2.5 Flash generates a grounded answer from the
                           assembled context. Strictly references provided data only.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import google.generativeai as genai
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import SessionLocal
from app.db.vector import embed_query as _embed_query_vec
from app.prompts.chatbot import ANSWER_PROMPT, GUARDRAIL_PROMPT
from app.utils.logger import get_logger

logger = get_logger(__name__)

settings = get_settings()
genai.configure(api_key=settings.GOOGLE_API_KEY)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GuardrailResult:
    is_relevant: bool
    category: str
    confidence: float
    reason: str

    @property
    def rejection_message(self) -> str:
        if self.category == "unsafe":
            return "I can only help with questions about your bank statements and financial transactions."
        return (
            "I'm specialised in bank statement analysis. "
            "Please ask me about your transactions, spending, balances, or financial patterns."
        )


@dataclass
class RetrievedChunk:
    chunk_id: str
    chunk_index: int
    chunk_text: str          # raw JSON string stored in DB
    date_range: str
    transaction_ids: List[str]
    transaction_amounts: List[float]
    transaction_dates: List[str]
    previous_chunk: Optional[str]
    next_chunk: Optional[str]
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    final_score: float = 0.0
    is_neighbor: bool = False    # True = fetched for graph context, not a direct hit


@dataclass
class ChatResponse:
    answer: str
    query: str
    account_id: str
    guardrail_passed: bool
    guardrail_category: str
    sources: List[Dict[str, Any]]
    chunks_used: int
    pipeline_steps: List[str]


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def chat_with_statements(
    db: Session,
    account_id: UUID,
    query: str,
    top_k: int = 5,
) -> ChatResponse:
    """
    GraphRAG pipeline: guardrails → dual search → rerank → graph expand → LLM answer.

    Args:
        db:         Active SQLAlchemy session.
        account_id: UUID of the account to search within.
        query:      Raw user question.
        top_k:      Number of top chunks to use for answer generation.

    Returns:
        ChatResponse with the answer and full pipeline metadata.
    """
    steps: List[str] = []
    loop = asyncio.get_running_loop()

    # ── Step 1: Guardrails ────────────────────────────────────────────────────
    steps.append("guardrail_check")
    logger.info("Chat pipeline started | account=%s | query=%r", account_id, query[:80])

    guardrail = await loop.run_in_executor(None, _run_guardrail_sync, query)
    logger.info(
        "Guardrail result | relevant=%s | category=%s | confidence=%.2f",
        guardrail.is_relevant, guardrail.category, guardrail.confidence,
    )

    if not guardrail.is_relevant:
        steps.append("guardrail_rejected")
        return ChatResponse(
            answer=guardrail.rejection_message,
            query=query,
            account_id=str(account_id),
            guardrail_passed=False,
            guardrail_category=guardrail.category,
            sources=[],
            chunks_used=0,
            pipeline_steps=steps,
        )

    steps.append("guardrail_passed")

    # ── Step 2: Embed query ───────────────────────────────────────────────────
    steps.append("query_embedding")
    query_embedding: List[float] = await loop.run_in_executor(None, _embed_query_vec, query)
    logger.info("Query embedded | dims=%d", len(query_embedding))

    # ── Steps 3a + 3b: Dual search (parallel, separate sessions) ─────────────
    steps.append("dual_search")

    # Each executor thread gets its own DB session to avoid concurrent-access errors
    def semantic_task():
        return _semantic_search_sync(db, account_id, query_embedding, 10)

    def keyword_task():
        kw_db = SessionLocal()
        try:
            return _keyword_search_sync(kw_db, account_id, query, query_embedding, 10)
        finally:
            kw_db.close()

    semantic_future = loop.run_in_executor(None, semantic_task)
    keyword_future = loop.run_in_executor(None, keyword_task)
    semantic_results, keyword_results = await asyncio.gather(semantic_future, keyword_future)
    logger.info(
        "Dual search complete | semantic=%d | keyword=%d",
        len(semantic_results), len(keyword_results),
    )

    # ── Step 4: Merge + deduplicate ───────────────────────────────────────────
    merged = _merge_results(semantic_results, keyword_results)
    logger.info("Merged results | unique_chunks=%d", len(merged))

    # ── Step 5: Re-rank ───────────────────────────────────────────────────────
    steps.append("rerank")
    query_terms = _extract_query_terms(query)
    reranked = _rerank(merged, query_terms)[:top_k]
    logger.info(
        "Re-rank complete | top_k=%d | best_score=%.4f",
        len(reranked),
        reranked[0].final_score if reranked else 0.0,
    )

    # ── Step 6: Graph expansion ───────────────────────────────────────────────
    steps.append("graph_expansion")
    context_chunks = await loop.run_in_executor(
        None, _expand_graph_neighbors, db, reranked
    )
    logger.info(
        "Graph expanded | direct_hits=%d | with_neighbors=%d",
        len(reranked), len(context_chunks),
    )

    # ── Step 7: LLM answer generation ────────────────────────────────────────
    steps.append("llm_answer")
    answer = await loop.run_in_executor(
        None, _generate_answer_sync, query, context_chunks
    )
    logger.info("Answer generated | length=%d chars", len(answer))

    # Build source summary (direct hits only, not neighbors)
    sources = [
        {
            "chunk_index": c.chunk_index,
            "date_range": c.date_range,
            "semantic_score": round(c.semantic_score, 4),
            "keyword_score": round(c.keyword_score, 4),
            "final_score": round(c.final_score, 4),
            "transaction_count": len(c.transaction_ids),
            "amounts": c.transaction_amounts,
            "dates": c.transaction_dates,
        }
        for c in reranked
    ]

    return ChatResponse(
        answer=answer,
        query=query,
        account_id=str(account_id),
        guardrail_passed=True,
        guardrail_category=guardrail.category,
        sources=sources,
        chunks_used=len(context_chunks),
        pipeline_steps=steps,
    )


# ---------------------------------------------------------------------------
# Step 1: Guardrail (sync — runs in thread pool)
# ---------------------------------------------------------------------------

def _run_guardrail_sync(query: str) -> GuardrailResult:
    """
    Ask Gemini to classify the query. Fails safe — if the API errors,
    we assume the query is relevant and let it through.
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = GUARDRAIL_PROMPT.format(query=query)
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
        result = json.loads(response.text)
        return GuardrailResult(
            is_relevant=bool(result.get("is_relevant", True)),
            category=result.get("category", "general_finance"),
            confidence=float(result.get("confidence", 1.0)),
            reason=result.get("reason", ""),
        )
    except Exception as exc:
        logger.warning("Guardrail check failed (failing open) | error=%s", exc)
        return GuardrailResult(
            is_relevant=True,
            category="general_finance",
            confidence=0.5,
            reason="guardrail_api_error_fail_open",
        )


# ---------------------------------------------------------------------------
# Step 3a: Semantic search (sync — runs in thread pool)
# ---------------------------------------------------------------------------

def _semantic_search_sync(
    db: Session,
    account_id: UUID,
    query_embedding: List[float],
    limit: int,
) -> List[RetrievedChunk]:
    """pgvector cosine similarity search."""
    embedding_str = str(query_embedding)
    sql = text("""
        SELECT
            chunk_id, chunk_index, chunk_text, date_range,
            transaction_ids, transaction_amounts, transaction_dates,
            previous_chunk, next_chunk,
            1 - (description_embedding <=> :query_embedding) AS similarity
        FROM chunks
        WHERE account_id = :account_id
          AND description_embedding IS NOT NULL
        ORDER BY description_embedding <=> :query_embedding
        LIMIT :limit
    """)
    rows = db.execute(
        sql,
        {"query_embedding": embedding_str, "account_id": str(account_id), "limit": limit},
    ).fetchall()

    return [
        RetrievedChunk(
            chunk_id=str(row.chunk_id),
            chunk_index=row.chunk_index,
            chunk_text=row.chunk_text,
            date_range=row.date_range or "Unknown",
            transaction_ids=row.transaction_ids or [],
            transaction_amounts=row.transaction_amounts or [],
            transaction_dates=row.transaction_dates or [],
            previous_chunk=str(row.previous_chunk) if row.previous_chunk else None,
            next_chunk=str(row.next_chunk) if row.next_chunk else None,
            semantic_score=float(row.similarity),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Step 3b: Keyword search (sync — runs in thread pool)
# ---------------------------------------------------------------------------

def _keyword_search_sync(
    db: Session,
    account_id: UUID,
    query: str,
    query_embedding: List[float],
    limit: int,
) -> List[RetrievedChunk]:
    """
    PostgreSQL ILIKE search across chunk_text (which contains transaction descriptions).
    Also fetches semantic similarity so re-ranking has both scores.
    """
    terms = _extract_query_terms(query)
    if not terms:
        return []

    # Build ILIKE conditions for each term
    like_clauses = " OR ".join(
        f"chunk_text ILIKE :term_{i}" for i in range(len(terms))
    )
    params: Dict[str, Any] = {
        "account_id": str(account_id),
        "query_embedding": str(query_embedding),
        "limit": limit,
    }
    for i, term in enumerate(terms):
        params[f"term_{i}"] = f"%{term}%"

    sql = text(f"""
        SELECT
            chunk_id, chunk_index, chunk_text, date_range,
            transaction_ids, transaction_amounts, transaction_dates,
            previous_chunk, next_chunk,
            1 - (description_embedding <=> :query_embedding) AS similarity
        FROM chunks
        WHERE account_id = :account_id
          AND ({like_clauses})
        ORDER BY similarity DESC
        LIMIT :limit
    """)

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception as exc:
        logger.warning("Keyword search failed | error=%s", exc)
        return []

    return [
        RetrievedChunk(
            chunk_id=str(row.chunk_id),
            chunk_index=row.chunk_index,
            chunk_text=row.chunk_text,
            date_range=row.date_range or "Unknown",
            transaction_ids=row.transaction_ids or [],
            transaction_amounts=row.transaction_amounts or [],
            transaction_dates=row.transaction_dates or [],
            previous_chunk=str(row.previous_chunk) if row.previous_chunk else None,
            next_chunk=str(row.next_chunk) if row.next_chunk else None,
            semantic_score=float(row.similarity),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Step 4: Merge + deduplicate
# ---------------------------------------------------------------------------

def _merge_results(
    semantic: List[RetrievedChunk],
    keyword: List[RetrievedChunk],
) -> List[RetrievedChunk]:
    """
    Union of semantic and keyword result sets.
    If a chunk appears in both, preserve the higher semantic score.
    """
    seen: Dict[str, RetrievedChunk] = {}
    for chunk in semantic:
        seen[chunk.chunk_id] = chunk
    for chunk in keyword:
        if chunk.chunk_id not in seen:
            seen[chunk.chunk_id] = chunk
        else:
            # Keep the higher semantic score
            existing = seen[chunk.chunk_id]
            existing.semantic_score = max(existing.semantic_score, chunk.semantic_score)
    return list(seen.values())


# ---------------------------------------------------------------------------
# Step 5: Re-rank
# ---------------------------------------------------------------------------

def _extract_query_terms(query: str) -> List[str]:
    """
    Extract meaningful search terms from a query.
    Filters out common stop words to improve keyword matching relevance.
    """
    stop_words = {
        "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and",
        "or", "but", "i", "my", "me", "did", "do", "was", "were", "are",
        "how", "what", "when", "where", "which", "who", "this", "that",
        "much", "many", "any", "all", "show", "tell", "find", "get",
    }
    words = re.findall(r"[a-zA-Z0-9₹$]+", query.lower())
    return [w for w in words if w not in stop_words and len(w) > 2]


def _keyword_hit_ratio(chunk: RetrievedChunk, terms: List[str]) -> float:
    """
    Fraction of query terms that appear anywhere in the chunk text.
    Returns value in [0, 1].
    """
    if not terms:
        return 0.0
    text_lower = chunk.chunk_text.lower()
    hits = sum(1 for t in terms if t in text_lower)
    return hits / len(terms)


def _rerank(chunks: List[RetrievedChunk], query_terms: List[str]) -> List[RetrievedChunk]:
    """
    Compute final_score = 0.65 × semantic_score + 0.35 × keyword_hit_ratio.
    Sort descending.
    """
    for chunk in chunks:
        chunk.keyword_score = _keyword_hit_ratio(chunk, query_terms)
        chunk.final_score = 0.65 * chunk.semantic_score + 0.35 * chunk.keyword_score
    return sorted(chunks, key=lambda c: c.final_score, reverse=True)


# ---------------------------------------------------------------------------
# Step 6: Graph expansion (sync — runs in thread pool)
# ---------------------------------------------------------------------------

def _expand_graph_neighbors(
    db: Session,
    top_chunks: List[RetrievedChunk],
) -> List[RetrievedChunk]:
    """
    For each top-K chunk, fetch its immediate prev and next neighbours from
    the linked-list graph. Neighbours are added as context (marked is_neighbor=True)
    and deduplicated against existing chunks.

    This is the 'graph' in GraphRAG — we traverse edges (prev/next links) to
    gather surrounding context beyond the directly ranked chunks.
    """
    existing_ids = {c.chunk_id for c in top_chunks}
    neighbor_ids_to_fetch: List[str] = []

    for chunk in top_chunks:
        if chunk.previous_chunk and chunk.previous_chunk not in existing_ids:
            neighbor_ids_to_fetch.append(chunk.previous_chunk)
        if chunk.next_chunk and chunk.next_chunk not in existing_ids:
            neighbor_ids_to_fetch.append(chunk.next_chunk)

    if not neighbor_ids_to_fetch:
        return list(top_chunks)

    # Deduplicate neighbor IDs before querying
    unique_neighbor_ids = list(dict.fromkeys(neighbor_ids_to_fetch))

    try:
        placeholders = ", ".join(f":id_{i}" for i in range(len(unique_neighbor_ids)))
        params = {f"id_{i}": nid for i, nid in enumerate(unique_neighbor_ids)}
        sql = text(f"""
            SELECT chunk_id, chunk_index, chunk_text, date_range,
                   transaction_ids, transaction_amounts, transaction_dates,
                   previous_chunk, next_chunk
            FROM chunks
            WHERE chunk_id IN ({placeholders})
            ORDER BY chunk_index
        """)
        rows = db.execute(sql, params).fetchall()
    except Exception as exc:
        logger.warning("Graph neighbor fetch failed | error=%s", exc)
        return list(top_chunks)

    neighbors: List[RetrievedChunk] = [
        RetrievedChunk(
            chunk_id=str(row.chunk_id),
            chunk_index=row.chunk_index,
            chunk_text=row.chunk_text,
            date_range=row.date_range or "Unknown",
            transaction_ids=row.transaction_ids or [],
            transaction_amounts=row.transaction_amounts or [],
            transaction_dates=row.transaction_dates or [],
            previous_chunk=str(row.previous_chunk) if row.previous_chunk else None,
            next_chunk=str(row.next_chunk) if row.next_chunk else None,
            is_neighbor=True,
        )
        for row in rows
    ]

    # Merge: direct hits first (sorted by final_score), then neighbours (sorted by chunk_index)
    # This ensures LLM sees the most relevant chunks first, with context around them
    result = list(top_chunks) + neighbors
    logger.debug("Graph expansion | added %d neighbor chunks", len(neighbors))
    return result


# ---------------------------------------------------------------------------
# Step 7: LLM answer generation (sync — runs in thread pool)
# ---------------------------------------------------------------------------

def _build_context(chunks: List[RetrievedChunk]) -> str:
    """
    Parse each chunk's JSON text and format it into a clean context block
    for the LLM. Sorted by chunk_index for chronological flow.
    """
    sorted_chunks = sorted(chunks, key=lambda c: c.chunk_index)
    sections: List[str] = []

    for chunk in sorted_chunks:
        label = "[CONTEXT]" if chunk.is_neighbor else "[RELEVANT]"
        try:
            data = json.loads(chunk.chunk_text)
            transactions = data.get("transactions", [])
            summary = data.get("summary", {})

            tx_lines = []
            for tx in transactions:
                date_str = tx.get("date") or "Unknown date"
                desc = tx.get("description") or "No description"
                amount = tx.get("amount", 0)
                tx_type = tx.get("type", "")
                balance = tx.get("balance")
                balance_str = f" | balance: {balance}" if balance else ""
                tx_lines.append(
                    f"  • {date_str} | {desc} | {tx_type} {amount}{balance_str}"
                )

            section = (
                f"{label} Chunk {chunk.chunk_index} | Range: {chunk.date_range}\n"
                + "\n".join(tx_lines)
                + f"\n  Summary: total_amount={summary.get('total_amount', 'N/A')}"
            )
        except (json.JSONDecodeError, KeyError):
            # Fallback: use raw text
            section = f"{label} Chunk {chunk.chunk_index} | {chunk.chunk_text[:300]}"

        sections.append(section)

    return "\n\n".join(sections)


def _generate_answer_sync(query: str, context_chunks: List[RetrievedChunk]) -> str:
    """
    Call Gemini 2.5 Flash with the assembled context to produce a grounded answer.
    """
    context = _build_context(context_chunks)
    prompt = ANSWER_PROMPT.format(context=context, query=query)

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.1},
    )
    return response.text.strip()
