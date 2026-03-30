"""
Auth Routes — Login, Signup, OTP Verification, and Resend endpoints.

Flow:
  Signup: POST /signup → sends OTP → POST /verify-otp → JWT issued
  Login:  POST /login  → sends OTP → POST /verify-otp → JWT issued
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.utils.dependencies import get_db
from app.utils.security import create_access_token
from app.service.auth_service import (
    create_user,
    authenticate_user,
    create_otp,
    verify_otp,
    check_resend_cooldown,
)
from app.utils.email_utils import send_otp_email
from app.schema.auth import (
    SignupRequest,
    LoginRequest,
    OTPVerifyRequest,
    OTPResendRequest,
    AuthResponse,
    OTPSentResponse,
)

router = APIRouter()


@router.post("/signup", response_model=OTPSentResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 1 of Signup — creates the user account and sends an OTP.
    The JWT is only issued after the OTP is verified.
    """
    try:
        await create_user(db=db, username=request.username, email=request.email, password=request.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user.")

    try:
        code = await create_otp(db=db, email=request.email, purpose="signup")
        await send_otp_email(email=request.email, otp_code=code, purpose="signup")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to send OTP: {str(e)}")

    return OTPSentResponse(message="Account created. Check your email for the verification code.", email=request.email)


@router.post("/login", response_model=OTPSentResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 1 of Login — validates credentials, then sends an OTP.
    The JWT is only issued after the OTP is verified.
    """
    try:
        await authenticate_user(db=db, email=request.email, password=request.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error during login.")

    try:
        code = await create_otp(db=db, email=request.email, purpose="login")
        await send_otp_email(email=request.email, otp_code=code, purpose="login")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to send OTP: {str(e)}")

    return OTPSentResponse(message="OTP sent to your email. Please verify to complete login.", email=request.email)


@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp_endpoint(request: OTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 2 of Login/Signup — verifies the OTP and issues a JWT on success.
    For signup, also marks the user as verified.
    """
    try:
        await verify_otp(db=db, email=request.email, otp_code=request.otp_code, purpose=request.purpose)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Fetch the user
    result = await db.execute(select(User).filter(User.email == request.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Mark as verified on signup
    if request.purpose == "signup" and not user.is_verified:
        user.is_verified = True
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.user_id)})

    return AuthResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        message="Verified successfully.",
        access_token=access_token,
        token_type="bearer",
    )


@router.post("/resend-otp", response_model=OTPSentResponse)
async def resend_otp(request: OTPResendRequest, db: AsyncSession = Depends(get_db)):
    """
    Resend a new OTP. Enforces a 60-second cooldown per email+purpose.
    """
    # Verify user exists before sending
    result = await db.execute(select(User).filter(User.email == request.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this email.")

    try:
        await check_resend_cooldown(db=db, email=request.email, purpose=request.purpose)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    try:
        code = await create_otp(db=db, email=request.email, purpose=request.purpose)
        await send_otp_email(email=request.email, otp_code=code, purpose=request.purpose)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to send OTP: {str(e)}")

    return OTPSentResponse(message="A new OTP has been sent to your email.", email=request.email)
