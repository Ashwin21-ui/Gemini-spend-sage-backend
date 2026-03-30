from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# Transform standard generic psycopg2 URL string into an explicit asyncpg protocol string
ASYNC_DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_recycle=3600,
    pool_pre_ping=True,
    connect_args={"timeout": 10}
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

Base = declarative_base()


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_context():
    """Async context manager for database sessions with proper cleanup on error."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.exception("Database transaction failed")
            raise
