"""
Application Configuration
Loads environment variables and provides settings
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    DATABASE_URL: str
    GOOGLE_API_KEY: str

    # JWT
    JWT_SECRET_KEY: str = "your-very-secure-secret-key-change-in-production"

    # SMTP Email
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM: str = "Spend Sage <noreply@spendsage.app>"

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
