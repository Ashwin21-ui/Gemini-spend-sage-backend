import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv(override=True)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def embed_text(text: str):
    result = genai.embeddings.embed_content(
        model="text-embedding-004",
        content=text,
        task_type="retrieval_document"
    )
    return result["embedding"]
