import google.generativeai as genai
import os
from dotenv import load_dotenv
from app.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv(override=True)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def embed_text(text: str):
    """Generate vector embeddings using Google's Generative AI API.
    
    Uses the gemini-embedding-001 model which is stable and widely available.
    Returns 3072-dimensional embedding vectors.
    """
    try:
        logger.debug(f"[VECTOR_SERVICE] Generating embedding for text ({len(text)} chars)...")
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        embedding = result["embedding"]
        logger.debug(f"[VECTOR_SERVICE] ✓ Embedding generated: {len(embedding)} dimensions")
        return embedding
    except Exception as e:
        logger.error(f"[VECTOR_SERVICE] ✗ Error generating embedding: {str(e)}")
        raise
