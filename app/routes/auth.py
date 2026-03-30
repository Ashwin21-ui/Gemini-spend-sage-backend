from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.base import SessionLocal
from app.service.auth_service import create_user, authenticate_user
from app.utils.security import create_access_token
from app.schema.auth import SignupRequest, LoginRequest, AuthResponse
from app.utils.dependencies import get_db

router = APIRouter()

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user with a unique username and email."""
    try:
        user = await create_user(
            db=db,
            username=request.username,
            email=request.email,
            password=request.password
        )
        return AuthResponse(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            message="User created successfully"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user"
        )

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate an existing user via email and password and issue a JWT token."""
    try:
        user = await authenticate_user(
            db=db,
            email=request.email,
            password=request.password
        )
        
        # Generate 7-day token
        access_token = create_access_token(data={"sub": str(user.user_id)})
        
        return AuthResponse(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            message="Login successful",
            access_token=access_token,
            token_type="bearer"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error logging in"
        )
