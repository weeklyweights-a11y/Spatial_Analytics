"""FastAPI dependencies for auth and shared services."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Callable, Optional
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.core.face_matcher import FaceMatcher
from backend.db.database import get_db
from backend.db.models import User

settings = get_settings()
ALGORITHM = "HS256"


@dataclass
class CurrentUser:
    """Authenticated user context."""

    id: UUID
    username: str
    role: str


def get_face_matcher(request: Request) -> FaceMatcher:
    """Return singleton FaceMatcher from app state."""
    return request.app.state.face_matcher


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or expired token", "code": "UNAUTHORIZED"},
        ) from exc


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    access_token: Annotated[Optional[str], Cookie(alias=settings.JWT_COOKIE_NAME)] = None,
) -> CurrentUser:
    """Extract JWT from Authorization header or httpOnly cookie."""
    token: Optional[str] = None
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required", "code": "UNAUTHORIZED"},
        )

    payload = _decode_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail={"error": "Invalid token", "code": "UNAUTHORIZED"})

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "User not found", "code": "UNAUTHORIZED"})

    return CurrentUser(id=user.id, username=user.username, role=user.role)


def require_role(allowed: list[str]) -> Callable:
    """Dependency factory checking role membership."""

    async def _checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Insufficient permissions", "code": "FORBIDDEN"},
            )
        return user

    return _checker


def create_access_token(username: str, role: str, expires_at: datetime) -> str:
    """Issue JWT access token."""
    return jwt.encode(
        {"sub": username, "role": role, "exp": expires_at},
        settings.JWT_SECRET,
        algorithm=ALGORITHM,
    )
