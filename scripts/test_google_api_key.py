import asyncio
import google.generativeai as genai

# Hardcoded API key
API_KEY = "AIzaSyCkfPOPZXDKNn8hhgu3JrA62wIgC93d44k"
genai.configure(api_key=API_KEY)

TEST_TEXT = "Hello, this is a test embedding!"

# Async Gemini embedding-001 (query embedding)
async def embed_query_async(text: str):
    try:
        result = await genai.embed_content_async(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_query",
            
        )
        embedding = result["embedding"]
        print("✅ gemini-embedding-001 query embedding length:", len(embedding))
        return embedding
    except Exception as e:
        print("❌ gemini-embedding-001 query embedding failed:", e)

# Synchronous Gemini 2.5-flash (normal text)
def send_to_flash(text: str):
    try:
        result = genai.generate(
            model="models/gemini-2.5-flash",
            prompt=text
        )
        output = result.text if hasattr(result, "text") else str(result)
        print("✅ gemini-2.5-flash output:", output)
        return output
    except Exception as e:
        print("❌ gemini-2.5-flash request failed:", e)

# Main async runner
async def main():
    await embed_query_async(TEST_TEXT)
    send_to_flash(TEST_TEXT)

if __name__ == "__main__":
    asyncio.run(main())