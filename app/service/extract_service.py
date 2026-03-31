"""
Async Bank Statement Extraction Service

Flow:
  1. Check data/ cache for pre-existing JSON (avoids redundant Gemini API calls)
  2. On cache miss → split PDF into 10-page chunks
  3. Extract transactions from each chunk via Gemini 2.5 Flash (avoids truncation)
  4. Merge all chunk results + recalculate summary
  5. Validate extracted JSON structure
  6. Persist cache to data/ directory
  7. Save to database via save_bank_statement
"""

import json
import asyncio
from pathlib import Path
from typing import Tuple, Dict, Any, List
from uuid import UUID
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession
import google.generativeai as genai
from pypdf import PdfReader, PdfWriter

from app.core.config import get_settings
from app.prompts.extract_bank_statement import BANK_STATEMENT_PROMPT
from app.repository.bank_repo import save_bank_statement
from app.utils.logger import get_logger

logger = get_logger(__name__)

settings = get_settings()
genai.configure(api_key=settings.GOOGLE_API_KEY)

DATA_DIR = Path("app/data")
_REQUIRED_KEYS = {"account_details", "transactions", "summary"}

_PDF_GUARDRAIL_PROMPT = """\
You are a document classifier. Examine this PDF and determine if it is a bank statement.

A bank statement typically contains:
  - Account holder name and account number
  - A list of financial transactions with dates and amounts
  - Debit/credit entries and/or running balances
  - Issued by a bank or financial institution

Return ONLY a valid JSON object — no markdown, no extra text:
{{
  "is_bank_statement": true or false,
  "confidence": 0.0 to 1.0,
  "document_type": "brief description of what this document is",
  "reason": "one sentence explanation"
}}
"""


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def extract_pdf_with_gemini(
    uploaded_pdf,
    db: AsyncSession,
    original_filename: str,
    user_id: UUID,
) -> Tuple[UUID, str, Dict[str, Any]]:
    """
    Extract structured bank statement data from a PDF using Gemini 2.5 Flash.

    Caching strategy:
        - If a JSON file for this PDF already exists in app/data/, reuse it.
        - Otherwise call the Gemini API (in a thread pool) and cache the result.

    Args:
        uploaded_pdf: File-like object from the upload (SpooledTemporaryFile).
        db:           Active SQLAlchemy session.
        original_filename: Original filename as uploaded by the client.
        user_id:      UUID of the uploading user.

    Returns:
        Tuple of (account_id, json_cache_path, extracted_json_dict)
    """
    logger.info("Starting PDF extraction | file=%s | user=%s", original_filename, user_id)

    await asyncio.to_thread(DATA_DIR.mkdir, parents=True, exist_ok=True)

    base_name = Path(original_filename).stem
    json_path = DATA_DIR / f"{base_name}_bank_statement.json"

    # ── Cache hit ────────────────────────────────────────────────────────────
    if json_path.exists():
        logger.info("Cache hit — reusing existing JSON | path=%s", json_path)
        extracted_json = await asyncio.to_thread(_read_json, json_path)
        _validate_extracted_json(extracted_json, json_path)
    else:
        # ── Cache miss: call Gemini in thread pool ───────────────────────────
        logger.info("Cache miss — calling Gemini API | file=%s", original_filename)
        pdf_bytes = await asyncio.to_thread(uploaded_pdf.read)
        logger.info("PDF read complete | size=%d bytes", len(pdf_bytes))

        # ── Guardrail: reject non-bank-statement PDFs ─────────────────────────
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _check_pdf_is_bank_statement_sync, pdf_bytes, original_filename
        )

        extracted_json = await loop.run_in_executor(
            None, _call_gemini_chunked_sync, pdf_bytes, original_filename
        )

        _validate_extracted_json(extracted_json, original_filename)
        await asyncio.to_thread(_write_json, json_path, extracted_json)
        logger.info("JSON cached | path=%s", json_path)

    # ── Persist to database ──────────────────────────────────────────────────
    logger.info("Saving to database | file=%s", original_filename)
    account_id = await save_bank_statement(db, extracted_json, user_id)
    logger.info("Extraction complete | account_id=%s | file=%s", account_id, original_filename)

    return account_id, str(json_path), extracted_json


# ---------------------------------------------------------------------------
# Synchronous helpers (run in thread pool or called from sync contexts)
# ---------------------------------------------------------------------------

def _call_gemini_chunked_sync(pdf_bytes: bytes, original_filename: str) -> Dict[str, Any]:
    """
    Extract from PDF by splitting into 10-page chunks to avoid response truncation.
    
    1. Split PDF into chunks (10 pages per chunk)
    2. Extract transactions from each chunk
    3. Merge results and recalculate summary
    4. Handles response truncation gracefully
    """
    logger.info("Gemini API request (chunked strategy) | file=%s", original_filename)
    
    # Split PDF into 10-page chunks
    try:
        chunks = _split_pdf_into_chunks(pdf_bytes, chunk_size=10)
        logger.info("PDF split into %d chunks | file=%s", len(chunks), original_filename)
    except Exception as e:
        logger.warning("PDF chunking failed, falling back to single request | error=%s", str(e))
        # Fall back to single request if chunking fails
        return _call_gemini_single_sync(pdf_bytes, original_filename)
    
    # Extract from each chunk
    chunk_results = []
    account_details = None
    
    for i, chunk_pdf_bytes in enumerate(chunks):
        logger.info("Processing chunk %d/%d | file=%s", i + 1, len(chunks), original_filename)
        
        try:
            result = _extract_from_chunk_sync(
                chunk_pdf_bytes, 
                chunk_num=i + 1, 
                total_chunks=len(chunks),
                original_filename=original_filename
            )
            
            # Capture account details from first chunk
            if account_details is None and "account_details" in result:
                account_details = result["account_details"]
            
            if "transactions" in result and result["transactions"]:
                chunk_results.extend(result["transactions"])
                logger.info(
                    "Extracted %d transactions from chunk %d | file=%s",
                    len(result["transactions"]), i + 1, original_filename
                )
        except Exception as chunk_err:
            logger.warning(
                "Chunk %d extraction failed | file=%s | error=%s",
                i + 1, original_filename, str(chunk_err)
            )
            # Continue with other chunks instead of failing completely
            continue
    
    if not chunk_results:
        raise ValueError(
            f"No transactions extracted from any chunk of '{original_filename}'. "
            "PDF may not be a valid bank statement."
        )
    
    # Merge and deduplicate transactions
    merged_transactions = _deduplicate_transactions(chunk_results)
    logger.info(
        "Merged chunks: %d total transactions | file=%s",
        len(merged_transactions), original_filename
    )
    
    # Reconstruct final JSON with recalculated summary
    final_json = {
        "account_details": account_details or {},
        "transactions": merged_transactions,
        "summary": _calculate_summary(merged_transactions)
    }
    
    logger.info(
        "Gemini extraction complete (chunked) | account_holder=%s | transactions=%d | file=%s",
        final_json.get("account_details", {}).get("account_holder_name", "unknown"),
        len(merged_transactions), original_filename
    )
    
    return final_json


def _call_gemini_single_sync(pdf_bytes: bytes, original_filename: str) -> Dict[str, Any]:
    """
    Fallback: Extract entire PDF in a single request (original approach).
    Used if chunking fails.
    """
    logger.info("Gemini API request (single request fallback) | file=%s", original_filename)
    
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        [
            {
                "role": "user",
                "parts": [
                    {"text": BANK_STATEMENT_PROMPT},
                    {"mime_type": "application/pdf", "data": pdf_bytes},
                ],
            }
        ],
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    )

    response_text = response.text.strip()
    logger.info("Gemini response received | file=%s | size=%d bytes", original_filename, len(response_text))
    
    # Try to extract JSON from markdown code blocks if present
    if response_text.startswith("```"):
        response_text = response_text.lstrip("`").lstrip("json").lstrip("`").strip()
        response_text = response_text.rstrip("`").strip()
    
    try:
        extracted_json: Dict[str, Any] = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(
            "JSON parsing failed | file=%s | error=%s | position=%d | line=%d | col=%d | response_size=%d",
            original_filename, str(e), e.pos, e.lineno, e.colno, len(response_text),
        )
        
        if not response_text.rstrip().endswith("}"):
            logger.error("Response appears truncated. Last 500 chars: %s", response_text[-500:])
            extracted_json = _attempt_truncated_recovery(response_text)
            if extracted_json:
                logger.warning("Recovered partial data from truncated response")
                return extracted_json
        
        logger.error("Raw response (first 1000 chars): %s", response_text[:1000])
        raise ValueError(
            f"Gemini API returned invalid JSON (possibly truncated). "
            f"Error at line {e.lineno}, column {e.colno}: {str(e)}"
        )
    
    return extracted_json


def _split_pdf_into_chunks(pdf_bytes: bytes, chunk_size: int = 10) -> List[bytes]:
    """
    Split PDF into chunks of N pages each.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        chunk_size: Number of pages per chunk (default 10)
    
    Returns:
        List of PDF bytes for each chunk
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    logger.info("PDF has %d total pages", total_pages)
    
    chunks = []
    for start_page in range(0, total_pages, chunk_size):
        end_page = min(start_page + chunk_size, total_pages)
        
        writer = PdfWriter()
        for page_num in range(start_page, end_page):
            writer.add_page(reader.pages[page_num])
        
        # Write chunk to bytes
        chunk_output = BytesIO()
        writer.write(chunk_output)
        chunk_output.seek(0)
        chunks.append(chunk_output.getvalue())
        
        logger.debug("Created chunk: pages %d-%d", start_page + 1, end_page)
    
    return chunks


def _extract_from_chunk_sync(
    chunk_pdf_bytes: bytes,
    chunk_num: int,
    total_chunks: int,
    original_filename: str
) -> Dict[str, Any]:
    """
    Extract transactions from a single PDF chunk via Gemini.
    
    Args:
        chunk_pdf_bytes: Raw bytes of PDF chunk
        chunk_num: Current chunk number (1-indexed)
        total_chunks: Total number of chunks
        original_filename: Original PDF filename
    
    Returns:
        Extracted data dict with account_details and transactions
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # Use a chunk-aware prompt that doesn't expect full summary
    chunk_prompt = f"""{BANK_STATEMENT_PROMPT}

NOTE: This is chunk {chunk_num} of {total_chunks}. Extract ONLY the transactions visible on these pages.
If this is chunk 1, also include the account details. For other chunks, set account_details to empty/null.
Do NOT include a summary calculation - leave the summary empty object."""
    
    response = model.generate_content(
        [
            {
                "role": "user",
                "parts": [
                    {"text": chunk_prompt},
                    {"mime_type": "application/pdf", "data": chunk_pdf_bytes},
                ],
            }
        ],
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    )

    response_text = response.text.strip()
    
    # Clean markdown if present
    if response_text.startswith("```"):
        response_text = response_text.lstrip("`").lstrip("json").lstrip("`").strip()
        response_text = response_text.rstrip("`").strip()
    
    try:
        chunk_data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(
            "Chunk %d JSON parse error | file=%s | line=%d col=%d",
            chunk_num, original_filename, e.lineno, e.colno
        )
        # Return partial data if available
        recovered = _attempt_truncated_recovery(response_text)
        if recovered:
            logger.warning("Recovered partial data from chunk %d", chunk_num)
            return recovered
        raise ValueError(f"Chunk {chunk_num} returned invalid JSON: {str(e)}")
    
    return chunk_data


def _deduplicate_transactions(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate transactions (by reference_no) and sort by date.
    Later occurrences override earlier ones (in case of conflicts).
    """
    seen = {}
    for txn in transactions:
        ref_no = txn.get("reference_no", "")
        if ref_no:
            seen[ref_no] = txn
        else:
            # If no reference number, try to use date + description as key
            key = f"{txn.get('date', '')}_{txn.get('description', '')}"
            if key not in seen:
                seen[key] = txn
    
    # Sort by date
    result = list(seen.values())
    result.sort(key=lambda x: x.get("date", ""))
    return result


def _calculate_summary(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Recalculate summary statistics from merged transactions.
    """
    total_credits = 0.0
    total_debits = 0.0
    credit_count = 0
    debit_count = 0
    opening_balance = None
    closing_balance = None
    
    for txn in transactions:
        amount = txn.get("amount", {})
        value = amount.get("value", 0.0)
        txn_type = amount.get("type", "")
        
        if txn_type == "credit":
            total_credits += float(value)
            credit_count += 1
        elif txn_type == "debit":
            total_debits += float(value)
            debit_count += 1
        
        # Track opening/closing balances
        balance_after = txn.get("balance_after_transaction", None)
        if balance_after is not None:
            if opening_balance is None:
                # First transaction's previous balance is opening
                opening_balance = float(balance_after) - (float(value) if txn_type == "credit" else -float(value))
            closing_balance = float(balance_after)
    
    return {
        "opening_balance": float(opening_balance) if opening_balance is not None else 0.0,
        "closing_balance": float(closing_balance) if closing_balance is not None else 0.0,
        "total_credits": float(total_credits),
        "total_debits": float(total_debits),
        "credit_count": credit_count,
        "debit_count": debit_count
    }


def _attempt_truncated_recovery(response_text: str) -> Dict[str, Any] | None:
    """
    Attempt to recover valid JSON from truncated Gemini response.
    
    Strategy: Find the last complete transaction object and close the JSON structure.
    """
    try:
        # Try to find the last complete transaction by working backwards
        last_close_brace = response_text.rfind("}")
        if last_close_brace == -1:
            return None
        
        # Find the last complete transaction object
        for i in range(last_close_brace, max(0, last_close_brace - 1000), -1):
            if response_text[i] == "}":
                # Try to close the JSON structure from this point
                candidate = response_text[:i+1]
                # Make sure we have a complete transactions array
                if '"transactions"' in candidate:
                    candidate += "\n}}"  # Close transactions array and main object
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
        return None
    except Exception as e:
        logger.debug("Truncated recovery attempt failed: %s", str(e))
        return None


def _read_json(path: Path) -> Dict[str, Any]:
    """Read and parse a JSON file (sync, for use with asyncio.to_thread)."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    """Serialize and write data to a JSON file (sync, for use with asyncio.to_thread)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _validate_extracted_json(data: Dict[str, Any], source: Any) -> None:
    """
    Lightweight structural validation of extracted Gemini output.
    Raises ValueError if required top-level keys are missing.
    """
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(
            f"Extracted JSON from '{source}' is missing required keys: {missing}"
        )
    if not isinstance(data.get("transactions"), list):
        raise ValueError(
            f"Extracted JSON from '{source}' has invalid 'transactions' field (expected list)"
        )


def _check_pdf_is_bank_statement_sync(pdf_bytes: bytes, original_filename: str) -> None:
    """
    Guardrail: verify the uploaded PDF is actually a bank statement.

    Sends the PDF bytes to Gemini 2.5 Flash for document classification.
    Raises ValueError if the document is not a bank statement.
    Fails open on API errors (avoids blocking uploads during Gemini outages).
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            [
                {
                    "role": "user",
                    "parts": [
                        {"text": _PDF_GUARDRAIL_PROMPT},
                        {"mime_type": "application/pdf", "data": pdf_bytes},
                    ],
                }
            ],
            generation_config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )
        
        response_text = response.text.strip()
        
        # Try to extract JSON from markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.lstrip("`").lstrip("json").lstrip("`").strip()
            response_text = response_text.rstrip("`").strip()
        
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(
                "PDF guardrail JSON parsing failed | file=%s | error=%s",
                original_filename, str(e),
            )
            # Fail open on parsing errors to not block uploads
            return
        
        is_bank_statement = bool(result.get("is_bank_statement", True))
        confidence = float(result.get("confidence", 1.0))
        document_type = result.get("document_type", "unknown")
        reason = result.get("reason", "")

        logger.info(
            "PDF guardrail | file=%s | is_bank_statement=%s | confidence=%.2f | type=%s",
            original_filename, is_bank_statement, confidence, document_type,
        )

        if not is_bank_statement:
            raise ValueError(
                f"Uploaded PDF does not appear to be a bank statement. "
                f"Detected: '{document_type}'. {reason}"
            )

    except ValueError:
        raise  # Re-raise our own rejection errors
    except Exception as exc:
        # API error — fail open so a Gemini outage doesn't block all uploads
        logger.warning(
            "PDF guardrail check failed (failing open) | file=%s | error=%s",
            original_filename, exc,
        )
