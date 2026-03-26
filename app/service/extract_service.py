"""
Bank Statement Extraction Service
Extracts structured data from PDF statements using Gemini
"""

import os
import json
from datetime import datetime
from app.core.config import get_settings
import google.generativeai as genai
from app.prompts.extract_bank_statement import BANK_STATEMENT_PROMPT
from app.repository.bank_repo import save_bank_statement
from app.utils.logger import get_logger

logger = get_logger(__name__)

settings = get_settings()
genai.configure(api_key=settings.GOOGLE_API_KEY)


def extract_pdf_with_gemini(uploaded_pdf, db, original_filename: str, user_id: int):
    """
    Extract structured bank statement JSON using Gemini 2.5 Pro
    - If this PDF was processed before (JSON exists), reuse it instead of calling Gemini.
    
    Args:
        uploaded_pdf: File object from upload
        db: Database session
        original_filename: Name of the uploaded file
        user_id: ID of the user uploading the statement
    
    Returns:
        Tuple: (account_id, json_path, extracted_json)
    """
    logger.info("=" * 80)
    logger.info(f"[EXTRACT_SERVICE] Starting PDF extraction for: {original_filename}")
    logger.info(f"[EXTRACT_SERVICE] User ID: {user_id}")
    logger.info("=" * 80)

    os.makedirs("app/data", exist_ok=True)
    logger.info("[EXTRACT_SERVICE] Data directory ready: app/data")

    # Make cache filename based on uploaded filename (no timestamp)
    base_name = os.path.splitext(original_filename)[0]
    json_path = f"app/data/{base_name}_bank_statement.json"

    # Check cache first
    if os.path.exists(json_path):
        logger.info(f"[EXTRACT_SERVICE] ✓ Using cached JSON at: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            extracted_json = json.load(f)
        logger.info(f"[EXTRACT_SERVICE] ✓ Loaded cached data with account: {extracted_json.get('account_details', {}).get('account_holder_name')}")

        logger.info("[EXTRACT_SERVICE] Proceeding to save_bank_statement...")
        account_id = save_bank_statement(db, extracted_json, user_id)
        logger.info(f"[EXTRACT_SERVICE] ✓ EXTRACTION COMPLETE for {original_filename}")
        logger.info("=" * 80)
        return account_id, json_path, extracted_json

    # Otherwise call Gemini
    logger.info(f"[EXTRACT_SERVICE] Cache miss, calling Gemini 2.5 Flash API...")
    pdf_bytes = uploaded_pdf.read()
    logger.info(f"[EXTRACT_SERVICE] PDF read: {len(pdf_bytes)} bytes")
    
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info(f"[EXTRACT_SERVICE] Sending API request to Gemini...")

    response = model.generate_content(
        [
            {
                "role": "user",
                "parts": [
                    {"text": BANK_STATEMENT_PROMPT},
                    {"mime_type": "application/pdf", "data": pdf_bytes}
                ]
            }
        ],
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json"
        }
    )
    logger.info(f"[EXTRACT_SERVICE] ✓ Gemini API response received")
    
    extracted_json = json.loads(response.text)
    logger.info(f"[EXTRACT_SERVICE] ✓ JSON parsed successfully")
    logger.info(f"[EXTRACT_SERVICE] Account holder: {extracted_json.get('account_details', {}).get('account_holder_name')}")
    logger.info(f"[EXTRACT_SERVICE] Transaction count: {len(extracted_json.get('transactions', []))}")

    # Save JSON output to cache for future use
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(extracted_json, f, indent=2, ensure_ascii=False)
    logger.info(f"[EXTRACT_SERVICE] ✓ Cached JSON saved to: {json_path}")

    # Save to database with user_id
    logger.info("[EXTRACT_SERVICE] Proceeding to save_bank_statement...")
    account_id = save_bank_statement(db, extracted_json, user_id)
    logger.info(f"[EXTRACT_SERVICE] ✓ EXTRACTION COMPLETE for {original_filename}")
    logger.info("=" * 80)

    return account_id, json_path, extracted_json
