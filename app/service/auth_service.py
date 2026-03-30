"""
Auth Service — User management, OTP generation, and verification logic.
"""
import random
import logging
from datetime import datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.user import User
from app.models.otp import OTP

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

OTP_EXPIRY_MINUTES = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def generate_otp() -> str:
    """Generate a cryptographically random 6-digit OTP."""
    return f"{random.SystemRandom().randint(0, 999999):06d}"


async def create_user(db: AsyncSession, username: str, email: str, password: str) -> User:
    """
    Create a new user with is_verified=False.
    Uniqueness is checked before creation.
    """
    result = await db.execute(
        select(User).filter((User.username == username) | (User.email == email))
    )
    existing = result.scalars().first()
    if existing:
        if existing.username == username:
            raise ValueError("Username is already taken.")
        if existing.email == email:
            raise ValueError("Email is already registered.")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"User created | username={username} | email={email}")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """
    Validate credentials. Returns User if valid — does NOT issue JWT here.
    JWT is only issued after OTP verification.
    """
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()
    if not user or not user.password_hash:
        raise ValueError("Invalid email or password.")
    if not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password.")
    logger.info(f"Credentials valid for | email={email}")
    return user


async def create_otp(db: AsyncSession, email: str, purpose: str) -> str:
    """
    Generate a fresh OTP, invalidate any existing ones for this email+purpose,
    and persist it. Returns the raw OTP code.
    """
    # Remove all previous OTPs for this email+purpose
    await db.execute(
        delete(OTP).where(OTP.email == email, OTP.purpose == purpose)
    )

    code = generate_otp()
    otp = OTP(
        email=email,
        otp_code=code,
        purpose=purpose,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    )
    db.add(otp)
    await db.commit()
    logger.info(f"OTP created | email={email} | purpose={purpose}")
    return code


async def verify_otp(db: AsyncSession, email: str, otp_code: str, purpose: str) -> bool:
    """
    Verify the provided OTP. Returns True if valid, raises ValueError otherwise.
    Marks the OTP as used on success.
    """
    result = await db.execute(
        select(OTP).where(
            OTP.email == email,
            OTP.purpose == purpose,
            OTP.is_used == False,
        ).order_by(OTP.created_at.desc())
    )
    otp = result.scalars().first()

    if not otp:
        raise ValueError("No active OTP found. Please request a new one.")
    if datetime.utcnow() > otp.expires_at:
        raise ValueError("OTP has expired. Please request a new one.")
    if otp.otp_code != otp_code:
        raise ValueError("Incorrect OTP. Please try again.")

    # Mark as used
    otp.is_used = True
    await db.commit()
    logger.info(f"OTP verified | email={email} | purpose={purpose}")
    return True


async def check_resend_cooldown(db: AsyncSession, email: str, purpose: str) -> None:
    """
    Raises ValueError if an OTP was created within the last 60 seconds.
    """
    result = await db.execute(
        select(OTP).where(
            OTP.email == email,
            OTP.purpose == purpose,
        ).order_by(OTP.created_at.desc())
    )
    last_otp = result.scalars().first()

    if last_otp:
        elapsed = (datetime.utcnow() - last_otp.created_at).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            raise ValueError(f"Please wait {remaining} seconds before requesting a new OTP.")


async def reset_password(db: AsyncSession, email: str, new_password: str) -> User:
    """
    Reset user password after OTP verification.
    """
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()
    if not user:
        raise ValueError("User not found.")
    
    user.password_hash = hash_password(new_password)
    await db.commit()
    await db.refresh(user)
    logger.info(f"Password reset | email={email}")
    return user
