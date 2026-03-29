import logging
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash the provided plain-text password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

async def create_user(db: Session, username: str, email: str, password: str) -> User:
    """
    Create a new user with unique username and email.
    """
    # Check uniqueness
    existing_user = db.execute(select(User).filter((User.username == username) | (User.email == email))).scalars().first()
    if existing_user:
        if existing_user.username == username:
            raise ValueError("Username is already taken.")
        if existing_user.email == email:
            raise ValueError("Email is already registered.")

    hashed_pw = hash_password(password)
    
    new_user = User(
        username=username,
        email=email,
        password_hash=hashed_pw
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"User created | username={username} | email={email}")
    return new_user

async def authenticate_user(db: Session, email: str, password: str) -> User:
    """
    Authenticate a user by email and password.
    Returns the User object if successful, raises ValueError otherwise.
    """
    user = db.execute(select(User).filter(User.email == email)).scalars().first()
    if not user:
        raise ValueError("Invalid email or password.")
        
    if not user.password_hash:
        raise ValueError("Invalid email or password.")
        
    if not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password.")
        
    logger.info(f"User successfully authenticated | email={email}")
    return user
