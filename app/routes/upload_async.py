"""
Async API Routes for Upload and Search
Clean, async endpoint implementations
"""

from fastapi import APIRouter, UploadFile, File, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from app.db.base import SessionLocal
from app.service.extract_service_async import extract_pdf_with_gemini_async
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload-bank-statement")
async def upload_bank_statement(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="UUID of the user"),
    db: Session = Depends(get_db)
):
    """
    Upload a bank statement PDF for async extraction.
    
    Validates file type, extracts data using Gemini, saves to database.
    
    Args:
        file: PDF file to upload
        user_id: User UUID as string
        db: Database session
        
    Returns:
        Success response with account_id and preview
        
    Raises:
        HTTPException: For invalid input or processing errors
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith(".pdf"):
            logger.warning(f"Invalid file type attempted: {file.filename}")
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )
        
        # Validate user_id format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            logger.warning(f"Invalid UUID format: {user_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format for user_id: {user_id}"
            )
        
        logger.info(f"Processing upload for user {user_uuid}: {file.filename}")
        
        # Extract and save
        account_id, json_path, extracted_json = await extract_pdf_with_gemini_async(
            file.file,
            db,
            original_filename=file.filename,
            user_id=user_uuid
        )
        
        logger.info(f"Successfully processed statement: {account_id}")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "account_id": str(account_id),
                "user_id": str(user_uuid),
                "filename": file.filename,
                "json_saved_at": json_path,
                "preview": extracted_json.get("account_details", {})
            }
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Upload rejected | file=%s | reason=%s", file.filename, str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing PDF file"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "service": "bank-statement-processor"}
    )
