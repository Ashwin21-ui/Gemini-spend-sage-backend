import google.generativeai as genai
import os
from dotenv import load_dotenv
from app.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv(override=True)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def embed_text(text: str):
    """Generate vector embedding for a DOCUMENT using Google's Generative AI API.

    Use this when indexing content (chunks, descriptions).
    Returns 3072-dimensional vectors (gemini-embedding-001).
    """
    try:
        logger.debug("[VECTOR] Generating document embedding (%d chars)...", len(text))
        result = genai.embed_content(
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


def embed_query(text: str):
    """Generate vector embedding for a QUERY using Google's Generative AI API.

    Use this at search/retrieval time — task_type='retrieval_query' produces
    vectors in the same space as retrieval_document embeddings but optimised
    for short query strings rather than long documents.
    Returns 3072-dimensional vectors.
    """
    try:
        logger.debug("[VECTOR] Generating query embedding (%d chars)...", len(text))
        result = genai.embed_content(
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
