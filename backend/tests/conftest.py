"""Pytest configuration and fixtures."""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

# Set env before app imports
def _default_database_url() -> str:
    """Use TEST_DB_PASSWORD, else DB_PASSWORD from .env, else CI default testpass."""
    password = os.environ.get("TEST_DB_PASSWORD")
    if not password:
        env_file = Path(__file__).resolve().parents[2] / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DB_PASSWORD="):
                    password = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    password = password or "testpass"
    return f"postgresql+asyncpg://spatialscore:{password}@localhost:5432/spatialscore_test"


os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key-minimum-32-characters-long")
os.environ.setdefault("DATABASE_URL", _default_database_url())
_db_url = os.environ["DATABASE_URL"]
os.environ.setdefault(
    "WORKER_DATABASE_URL",
    _db_url.replace("postgresql+asyncpg://", "postgresql://"),
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("FAISS_INDEX_PATH", "/tmp/spatialscore_test/faiss_index.bin")
os.environ.setdefault("EMBEDDING_MAP_PATH", "/tmp/spatialscore_test/embedding_map.json")
os.environ.setdefault("MODELS_DIR", "/tmp/spatialscore_test/models")

from backend.config import get_settings

get_settings.cache_clear()
from backend.api.deps import create_access_token
from backend.core.face_detector import Face
from backend.core.face_matcher import FaceMatcher
from backend.db.models import Base, User
from backend.main import create_app
from backend.middleware.rate_limit import limiter

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)


def _clear_rate_limits() -> None:
    """Reset slowapi in-memory counters between tests."""
    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "storage"):
        storage.storage.clear()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


def _ensure_phase4_schema(engine) -> None:
    """Apply Phase 4 columns/tables missing from older test DB create_all snapshots."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE zones ADD COLUMN IF NOT EXISTS floor_polygon JSONB"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    rule_name VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    zone VARCHAR(100),
                    floor INTEGER,
                    fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
                    acknowledged_at TIMESTAMPTZ,
                    acknowledged_by UUID REFERENCES users(id)
                )
                """
            )
        )


@pytest.fixture(scope="session")
def sync_engine():
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    try:
        Base.metadata.create_all(engine)
        _ensure_partitioned_activity_logs(engine)
        _ensure_phase4_schema(engine)
        yield engine
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")


def _ensure_partitioned_activity_logs(engine) -> None:
    """Replace ORM-created activity_logs with a range-partitioned parent + current hour child."""
    from datetime import datetime, timezone

    from sqlalchemy import text

    from backend.db.partitions import ensure_activity_log_partition

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS activity_logs CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE activity_logs (
                    id BIGSERIAL,
                    participant_id UUID NOT NULL REFERENCES participants(id),
                    camera_id VARCHAR(50) NOT NULL,
                    zone_id UUID NOT NULL REFERENCES zones(id),
                    activity VARCHAR(50) NOT NULL,
                    bbox JSONB,
                    confidence FLOAT,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (id, timestamp)
                ) PARTITION BY RANGE (timestamp)
                """
            )
        )
    ensure_activity_log_partition(engine, datetime.now(timezone.utc))


@pytest_asyncio.fixture
async def db_session(sync_engine):
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def face_matcher(tmp_path):
    settings = get_settings()
    matcher = FaceMatcher()
    matcher.index_path = tmp_path / "faiss.bin"
    matcher.map_path = tmp_path / "map.json"
    matcher.load()
    return matcher


class MockDetector:
    def detect(self, image, threshold=0.5):
        h, w = image.shape[:2]
        return [
            Face(
                bbox=np.array([w * 0.3, h * 0.3, w * 0.7, h * 0.7], dtype=np.float32),
                confidence=0.99,
                landmarks=np.array(
                    [[w * 0.4, h * 0.4], [w * 0.6, h * 0.4], [w * 0.5, h * 0.5], [w * 0.4, h * 0.6], [w * 0.6, h * 0.6]],
                    dtype=np.float32,
                ),
            )
        ]


class MockRecognizer:
    def align_face(self, image, landmarks, size=112):
        return cv2.resize(image, (size, size))

    def embed(self, aligned_face):
        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb) + 1e-8
        return emb


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    _clear_rate_limits()
    previous_enabled = getattr(limiter, "enabled", True)
    limiter.enabled = False
    yield
    limiter.enabled = previous_enabled
    _clear_rate_limits()


@pytest_asyncio.fixture(autouse=True)
async def _dispose_db_pool():
    """Avoid stale asyncpg connections across pytest-asyncio loops (Windows)."""
    yield
    from backend.db.database import engine

    await engine.dispose()


@pytest_asyncio.fixture
async def app(face_matcher):
    _clear_rate_limits()
    application = create_app()
    application.router.lifespan_context = _noop_lifespan
    application.state.face_matcher = face_matcher
    application.state.face_detector = MockDetector()
    application.state.face_recognizer = MockRecognizer()
    application.state.start_time = __import__("time").time()
    try:
        from backend.db.redis_client import init_redis

        await init_redis()
    except Exception:
        pass
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def admin_user(sync_engine):
    with Session(sync_engine) as session:
        for uname, role in [("testadmin", "admin"), ("testviewer", "viewer"), ("testoperator", "operator")]:
            existing = session.execute(select(User).where(User.username == uname)).scalar_one_or_none()
            if existing is None:
                session.add(
                    User(
                        id=uuid.uuid4(),
                        username=uname,
                        password_hash=pwd_context.hash("testpass123"),
                        role=role,
                    )
                )
        session.commit()
    return "testadmin", "testpass123"


@pytest.fixture(scope="session")
def admin_token(admin_user):
    """Issue JWT directly to avoid login rate limits in integration tests."""
    username, _ = admin_user
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return create_access_token(username, "admin", expires_at)


def make_face_jpeg() -> bytes:
    """Generate a minimal valid JPEG for upload tests."""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.rectangle(img, (60, 60), (140, 140), (200, 180, 160), -1)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def make_no_face_jpeg() -> bytes:
    """Landscape image with no face-like region for mock (empty detect override in test)."""
    img = np.zeros((100, 300, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


@pytest.fixture
def sample_face_jpeg():
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "sample_face.jpg").read_bytes()
