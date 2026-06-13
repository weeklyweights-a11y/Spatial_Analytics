"""Application configuration from environment variables."""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration — no scattered env reads."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://spatialscore:changeme@localhost:5432/spatialscore"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = ""
    JWT_EXPIRY_HOURS: int = 24
    JWT_COOKIE_NAME: str = "access_token"
    FAISS_INDEX_PATH: str = "/app/data/faiss/faiss_index.bin"
    EMBEDDING_MAP_PATH: str = "/app/data/faiss/embedding_map.json"
    MODELS_DIR: str = "/app/models"
    GCS_BUCKET: str = "spatialscore-data"
    LOG_LEVEL: str = "INFO"
    FACE_SIMILARITY_THRESHOLD: float = 0.5
    DUPLICATE_REGISTRATION_THRESHOLD: float = 0.6
    SCORING_FLUSH_INTERVAL: int = 60
    HEATMAP_SNAPSHOT_INTERVAL: int = 300
    MAX_REGISTRATION_STATIONS: int = 10
    CORS_ORIGINS: str = "http://localhost:3000,https://spatialscore.buildathon.co"

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


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
