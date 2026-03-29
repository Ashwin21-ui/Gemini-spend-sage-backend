"""
Test script to run various expected queries against the bank statement data.
Tests cover aggregation, keyword matching, dates, category extraction, and guardrails.
"""

import asyncio
from uuid import UUID

from app.db.base import SessionLocal
from app.service.chatbot_service import chat_with_statements


async def run_tests():
    account_id = UUID("6675929d-db49-4e8f-9eb4-78be816c2c1a")
    
    queries = [
        # Aggregation / Count
        "What is the total amount I spent at GR Thangamaligai?",
        # Specific transaction / Matching
        "How much was my LIC premium payment?",
        "Tell me about the NEFT from State Bank of India.",
        # Category / List
        "List all my ATM withdrawals and state the total number of them.",
        "What were my Amazon Pay or Amazon purchases?",
        # Dates / Filtering
        "Did I have any transactions on 2019-07-06?",
        # Guardrail
        "What is the capital of France?"
    ]

    print("════════════════════════════════════════════════════════")
    print("  RUNNING CHATBOT QUERIES (with Rate Limit spacing)")
    print("════════════════════════════════════════════════════════\n")

    for i, query in enumerate(queries, 1):
        db = SessionLocal()
        try:
            print(f"[{i}] Query: {query}")
            response = await chat_with_statements(
                db=db,
                account_id=account_id,
                query=query,
                top_k=4
            )
            print("Answer:")
            print(f"  {response.answer}")
            print(f"Sources Used: {response.chunks_used} chunks")
            if not response.guardrail_passed:
                print(f"Guardrail: REJECTED ({response.guardrail_category})")
            print("-" * 60)
            
            # Rate limit protection: wait 15 seconds to stay under 15 RPM
            if i < len(queries):
                print("Waiting 15s to respect Gemini API rate limits...\n")
                await asyncio.sleep(15)
                
        except Exception as e:
            print(f"Error executing query: {e}")
            if "429" in str(e):
                print("Rate limited! Waiting 30s...\n")
                await asyncio.sleep(30)
        finally:
            db.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
