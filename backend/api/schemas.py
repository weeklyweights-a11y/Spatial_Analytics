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
    cameras: list["CameraHealthStatus"] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    """Admin metrics."""

    total_registered: int
    faiss_index_size: int
    redis_memory_used_mb: float
    postgres_connection_pool: dict[str, Any]
    uptime_seconds: float
    events_in_stream: int = 0
    total_persons_tracked: int = 0
    cameras: dict[str, dict[str, Any]] = Field(default_factory=dict)
    heatmap_snapshots_total: int = 0
    alerts_fired_total: int = 0
    alerts_unacknowledged: int = 0
    energy_level_current: float = 0.0


class CameraHealthStatus(BaseModel):
    """Per-camera worker health."""

    camera_id: str
    status: str
    fps: Optional[float] = None
    persons_tracked: Optional[int] = None
    stale: bool = False


VALID_TRACKS = frozenset({"ai_ml", "web3", "devtools", "fintech", "health", "open"})

TRACK_LABELS = {
    "ai_ml": "AI/ML",
    "web3": "Web3",
    "devtools": "DevTools",
    "fintech": "FinTech",
    "health": "Health",
    "open": "Open",
}


class RadarAxis(BaseModel):
    """Radar chart axis."""

    axis: str
    value: float


class ScoreLeaderboardEntry(BaseModel):
    """Leaderboard row."""

    participant_id: UUID
    name: str
    team_name: str
    track: str = ""
    total_score: float
    rank: Optional[int] = None
    current_activity: Optional[str] = None
    current_zone: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ScoreLeaderboardResponse(BaseModel):
    """Leaderboard list response."""

    data: List[ScoreLeaderboardEntry]
    pagination: PaginationMeta
    total_participants: int


class ActivityBreakdown(BaseModel):
    """Per-activity minutes and points."""

    minutes: float
    points: float
    percentage: float


class ScoreDetailResponse(BaseModel):
    """Full score breakdown for score card."""

    participant_id: UUID
    name: str
    team_name: str
    track: str
    total_score: float
    rank: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    current_zone: Optional[str] = None
    current_activity: Optional[str] = None
    photo_base64: Optional[str] = None
    radar_data: List[RadarAxis] = Field(default_factory=list)
    breakdown: dict[str, ActivityBreakdown] = Field(default_factory=dict)
    registered_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class ActivityTimelineHour(BaseModel):
    """Hourly activity rollup."""

    hour: str
    zone: str
    primary_activity: str
    minutes: float


class ActivityTimelineResponse(BaseModel):
    """Timeline response."""

    timeline: List[ActivityTimelineHour]


class CameraResponse(BaseModel):
    """Camera list item."""

    id: str
    name: Optional[str] = None
    floor: Optional[int] = None
    rtsp_url: Optional[str] = None
    is_active: bool = True


class ActiveParticipant(BaseModel):
    """Currently active participant."""

    participant_id: str
    zone: str
    activity: str
    score: float
    last_seen: str
