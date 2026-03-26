"""
Spend Sage Backend — Application Entry Point

Async FastAPI application for intelligent bank statement processing.
Uses Google Gemini AI for extraction and pgvector for semantic search.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.upload_async import router as upload_router
from app.routes.search_async import router as search_router
from app.routes.chat_async import router as chat_router
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    logger.info("=" * 60)
    logger.info("Spend Sage Backend starting up")
    logger.info("=" * 60)
    yield
    logger.info("Spend Sage Backend shutting down")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Spend Sage Bank Statement API",
    description="Intelligent financial data extraction using Google Gemini AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api", tags=["Upload"])
app.include_router(search_router, prefix="/api", tags=["Search"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

@app.get("/", tags=["Meta"])
async def root():
    """Service info and available endpoints."""
    return {
        "service": "Spend Sage Bank Statement API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "upload": "/api/upload-bank-statement",
            "search": "/api/search-statements",
            "health": "/api/health",
        },
    }


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
