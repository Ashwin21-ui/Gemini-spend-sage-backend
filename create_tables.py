"""
Database Migration Script
Creates all tables with proper schema
"""

from app.db.base import Base, engine
from app.models import User, AccountDetails, Transaction, Chunk
from sqlalchemy import text

print("Attempting to enable pgvector extension...")
try:
    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
        print("✓ pgvector extension enabled")
except Exception as e:
    print(f"⚠ Warning: Could not enable pgvector extension")
    print(f"  Error: {str(e)}")
    print("\n  pgvector needs to be installed in PostgreSQL!")
    print("  Please run:")
    print("  brew install pgvector")
    print("\n  Then restart PostgreSQL server and run this script again.")

print("\nDropping all tables...")
Base.metadata.drop_all(bind=engine)

print("Creating all tables...")
try:
    Base.metadata.create_all(bind=engine)
    print("\n✓ Tables created successfully!")
    print("  Created tables:")
    print("    ✓ users")
    print("    ✓ account_details") 
    print("    ✓ transactions")
    print("    ✓ chunks (with vector embeddings)")
except Exception as e:
    print(f"\n✗ Error creating tables: {str(e)}")
    print("\nIf the error mentions 'type \"vector\" does not exist', pgvector extension needs to be installed in PostgreSQL.")
    print("Run: brew install pgvector")
    raise
