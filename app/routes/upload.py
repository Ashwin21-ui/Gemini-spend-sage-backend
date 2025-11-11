from fastapi import APIRouter, UploadFile, File, Depends
from app.db.base import SessionLocal
from app.service.extract_service import extract_pdf_with_gemini
from sqlalchemy.orm import Session

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
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported."}

    account_id, json_path, extracted_json = extract_pdf_with_gemini(
        file.file,
        db,
        original_filename=file.filename
    )

    return {
        "status": "success",
        "account_id": account_id,
        "json_saved_at": json_path,
        "preview": extracted_json.get("account_details", {})
    }
