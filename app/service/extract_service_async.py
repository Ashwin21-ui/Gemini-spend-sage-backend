"""
Async Bank Statement Extraction Service

Flow:
  1. Check data/ cache for pre-existing JSON (avoids redundant Gemini API calls)
  2. On cache miss → call Gemini 2.5 Flash in a thread pool (non-blocking)
  3. Validate extracted JSON structure
  4. Persist cache to data/ directory
  5. Save to database via save_bank_statement_async
"""

import json
import asyncio
from pathlib import Path
from typing import Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
import google.generativeai as genai

from app.core.config import get_settings
from app.prompts.extract_bank_statement import BANK_STATEMENT_PROMPT
from app.repository.bank_repo_async import save_bank_statement_async
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

async def extract_pdf_with_gemini_async(
    uploaded_pdf,
    db: Session,
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
            None, _call_gemini_sync, pdf_bytes, original_filename
        )

        _validate_extracted_json(extracted_json, original_filename)
        await asyncio.to_thread(_write_json, json_path, extracted_json)
        logger.info("JSON cached | path=%s", json_path)

    # ── Persist to database ──────────────────────────────────────────────────
    logger.info("Saving to database | file=%s", original_filename)
    account_id = await save_bank_statement_async(db, extracted_json, user_id)
    logger.info("Extraction complete | account_id=%s | file=%s", account_id, original_filename)

    return account_id, str(json_path), extracted_json


# ---------------------------------------------------------------------------
# Synchronous helpers (run in thread pool or called from sync contexts)
# ---------------------------------------------------------------------------

def _call_gemini_sync(pdf_bytes: bytes, original_filename: str) -> Dict[str, Any]:
    """
    Blocking Gemini API call — always run via run_in_executor, never directly
    in an async function.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("Gemini API request sent | file=%s", original_filename)

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

    extracted_json: Dict[str, Any] = json.loads(response.text)
    logger.info(
        "Gemini response parsed | account_holder=%s | transactions=%d",
        extracted_json.get("account_details", {}).get("account_holder_name", "unknown"),
        len(extracted_json.get("transactions", [])),
    )
    return extracted_json


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
        result = json.loads(response.text)
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
