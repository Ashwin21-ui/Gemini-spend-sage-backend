import jwt
from datetime import datetime, timedelta
from typing import Optional

# In production, securely load this from environment variables (os.environ or settings)
SECRET_KEY = "your-very-secure-secret-key-that-should-be-in-an-env-file"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Issue a new JWT token containing the payload data (`user_id`).
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Default expiry: 7 days
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
