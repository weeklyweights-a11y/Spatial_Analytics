"""Application configuration from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration — no scattered env reads."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://spatialscore:changeme@localhost:5432/spatialscore"
    WORKER_DATABASE_URL: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = ""
    JWT_EXPIRY_HOURS: int = 24
    JWT_COOKIE_NAME: str = "access_token"
    FAISS_INDEX_PATH: str = "/app/data/faiss/faiss_index.bin"
    EMBEDDING_MAP_PATH: str = "/app/data/faiss/embedding_map.json"
    MODELS_DIR: str = "/app/models"
    CONFIGS_DIR: str = "/app/configs"
    GCS_BUCKET: str = "spatialscore-data"
    LOG_LEVEL: str = "INFO"
    FACE_SIMILARITY_THRESHOLD: float = 0.5
    DUPLICATE_REGISTRATION_THRESHOLD: float = 0.6
    SCORING_FLUSH_INTERVAL: int = 60
    HEATMAP_SNAPSHOT_INTERVAL: int = 10
    MAX_REGISTRATION_STATIONS: int = 10
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Phase 2 camera worker
    DEIMV2_MODEL_PATH: str = ""
    DEIMV2_CONFIDENCE_THRESHOLD: float = 0.3
    FACE_RECOGNITION_INTERVAL_FRAMES: int = 20
    CAMERA_TARGET_FPS: float = 10.0
    CAMERA_HEARTBEAT_SECONDS: float = 10.0
    UNIDENTIFIED_TIMEOUT_SECONDS: float = 10.0
    CAMERA_FRAME_TTL_SECONDS: int = 5
    BYTETRACK_CONFIG_PATH: str = ""

    # Phase 5 sponsor reports
    EVENT_NAME: str = "SpatialScore Event"

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Refuse weak secrets at startup."""
        if not v or v == "changeme" or len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters and not 'changeme'")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic/psycopg2."""
        return self.DATABASE_URL.replace("+asyncpg", "")

    @property
    def worker_database_url(self) -> str:
        """Sync Postgres URL for camera worker name lookup."""
        if self.WORKER_DATABASE_URL:
            return self.WORKER_DATABASE_URL.replace("+asyncpg", "")
        return self.database_url_sync

    @property
    def deimv2_model_path(self) -> Path:
        if self.DEIMV2_MODEL_PATH:
            return Path(self.DEIMV2_MODEL_PATH)
        return Path(self.MODELS_DIR) / "deimv2_s_wholebody49.onnx"

    @property
    def bytetrack_config_path(self) -> Path:
        if self.BYTETRACK_CONFIG_PATH:
            return Path(self.BYTETRACK_CONFIG_PATH)
        primary = Path(self.CONFIGS_DIR) / "bytetrack.yaml"
        if primary.exists():
            return primary
        return Path(__file__).resolve().parents[1] / "configs" / "bytetrack.yaml"

    def load_bytetrack_config(self) -> dict[str, Any]:
        """Load ByteTrack params from YAML."""
        path = self.bytetrack_config_path
        if not path.exists():
            return {
                "track_activation_threshold": 0.25,
                "lost_track_buffer": 30,
                "minimum_matching_threshold": 0.8,
                "frame_rate": 10,
                "smoother_length": 5,
            }
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
