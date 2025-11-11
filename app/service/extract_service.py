import os
import json
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from app.prompts.extract_bank_statement import BANK_STATEMENT_PROMPT
from app.repository.bank_repo import save_bank_statement
from app.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv(override=True)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def extract_pdf_with_gemini(uploaded_pdf, db, original_filename: str):
    """
    Extract structured bank statement JSON using Gemini 2.5 Pro
    - If this PDF was processed before (JSON exists), reuse it instead of calling Gemini.
    """

    os.makedirs("app/data", exist_ok=True)

    # Make cache filename based on uploaded filename (no timestamp)
    base_name = os.path.splitext(original_filename)[0]
    json_path = f"app/data/{base_name}_bank_statement.json"

    # Check cache first
    if os.path.exists(json_path):
        logger.info(f"Using cached JSON for {original_filename} at {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            extracted_json = json.load(f)

        account_id = save_bank_statement(db, extracted_json)
        return account_id, json_path, extracted_json

    # Otherwise call Gemini
    pdf_bytes = uploaded_pdf.read()
    model = genai.GenerativeModel("gemini-2.5-pro")
    logger.info(f"Calling Gemini for bank statement extraction: {original_filename}")

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
    logger.info(f"Gemini response received for {original_filename}")
    extracted_json = json.loads(response.text)

    # Save to DB
    account_id = save_bank_statement(db, extracted_json)
    logger.info(f"Bank statement saved to DB with account_id: {account_id}")
    # Save JSON output to cache for future use
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(extracted_json, f, indent=2, ensure_ascii=False)

    return account_id, json_path, extracted_json
