"""Authentication endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import create_access_token
from backend.api.schemas import LoginRequest, TokenResponse
from backend.config import get_settings
from backend.db.database import get_db
from backend.db.models import User
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
settings = get_settings()


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate credentials and return JWT + httpOnly cookie."""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid username or password", "code": "INVALID_CREDENTIALS"},
        )

    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    token = create_access_token(user.username, user.role, expires_at)
    response.set_cookie(
        key=settings.JWT_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=settings.JWT_EXPIRY_HOURS * 3600,
    )
    payload = TokenResponse(token=token, role=user.role, expires_at=expires_at)
    return {"data": payload.model_dump()}


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear httpOnly auth cookie."""
    response.delete_cookie(key=settings.JWT_COOKIE_NAME)
    return {"data": {"logged_out": True}}
