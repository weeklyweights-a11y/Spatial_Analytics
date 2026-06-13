"""Pydantic v2 request/response schemas."""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard API error envelope."""

    error: str
    code: str


class PaginationMeta(BaseModel):
    """List pagination metadata."""

    page: int
    per_page: int
    total: int


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list wrapper."""

    data: List[T]
    pagination: PaginationMeta


class LoginRequest(BaseModel):
    """Login credentials."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token payload."""

    token: str
    role: str
    expires_at: datetime


class ParticipantResponse(BaseModel):
    """Participant profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: Optional[str] = None
    team_name: str
    track: str
    skills: Optional[List[str]] = None
    photo_path: Optional[str] = None
    embedding_id: Optional[int] = None
    registered_at: datetime
    opted_out: bool = False
    total_score: Optional[float] = None


class ParticipantListResponse(BaseModel):
    """Paginated participants."""

    data: List[ParticipantResponse]
    pagination: PaginationMeta


class HealthCheckDetail(BaseModel):
    """Individual health check result."""

    status: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """Health endpoint response (top-level, not wrapped in data)."""

    status: str
    checks: dict[str, HealthCheckDetail]
    uptime_seconds: float


class MetricsResponse(BaseModel):
    """Admin metrics."""

    total_registered: int
    faiss_index_size: int
    redis_memory_used_mb: float
    postgres_connection_pool: dict[str, Any]
    uptime_seconds: float


VALID_TRACKS = frozenset({"ai_ml", "web3", "devtools", "fintech", "health", "open"})

TRACK_LABELS = {
    "ai_ml": "AI/ML",
    "web3": "Web3",
    "devtools": "DevTools",
    "fintech": "FinTech",
    "health": "Health",
    "open": "Open",
}
