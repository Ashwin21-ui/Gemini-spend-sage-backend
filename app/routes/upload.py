from fastapi import APIRouter, UploadFile, File, Depends, Query
from app.db.base import SessionLocal
from app.service.extract_service import extract_pdf_with_gemini
from sqlalchemy.orm import Session
from uuid import UUID

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload-bank-statement")
async def upload_bank_statement(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="UUID of the user uploading the statement"),
    db: Session = Depends(get_db)
):
    """
    Upload a bank statement PDF for extraction and analysis.
    
    Args:
        file: PDF file to upload
        user_id: UUID of the user uploading the statement
        db: Database session
    
    Returns:
        Success response with account_id and preview
    """
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported."}

    # Convert user_id string to UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return {"error": f"Invalid UUID format for user_id: {user_id}"}

    account_id, json_path, extracted_json = extract_pdf_with_gemini(
        file.file,
        db,
        original_filename=file.filename,
        user_id=user_uuid
    )

    return {
        "status": "success",
        "account_id": str(account_id),
        "user_id": str(user_uuid),
        "json_saved_at": json_path,
        "preview": extracted_json.get("account_details", {})
    }
