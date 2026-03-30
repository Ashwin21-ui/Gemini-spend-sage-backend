import google.generativeai as genai
import os
from dotenv import load_dotenv
from app.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv(override=True)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

async def embed_text_async(text: str):
    """Generate vector embedding for a DOCUMENT using Google's Generative AI API natively async."""
    try:
        logger.debug("[VECTOR] Generating async document embedding (%d chars)...", len(text))
        result = await genai.embed_content_async(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_document",
        )
        embedding = result["embedding"]
        logger.debug("[VECTOR] Document embedding ready: %d dims", len(embedding))
        return embedding
    except Exception as e:
        logger.error("[VECTOR] Document embedding failed: %s", e)
        raise


async def embed_query_async(text: str):
    """Generate vector embedding for a QUERY natively async."""
    try:
        logger.debug("[VECTOR] Generating async query embedding (%d chars)...", len(text))
        result = await genai.embed_content_async(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_query",
        )
        embedding = result["embedding"]
        logger.debug("[VECTOR] Query embedding ready: %d dims", len(embedding))
        return embedding
    except Exception as e:
        logger.error("[VECTOR] Query embedding failed: %s", e)
        raise
