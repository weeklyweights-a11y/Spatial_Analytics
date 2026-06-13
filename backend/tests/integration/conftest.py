"""Integration tests require a running PostgreSQL instance."""

import os

import pytest
from sqlalchemy import text

from backend.config import get_settings
from backend.core.face_detector import FaceDetector
from backend.core.face_matcher import FaceMatcher
from backend.core.face_recognizer import FaceRecognizer
from backend.tests.integration.pipeline_helpers import REPO_ROOT, redis_available


@pytest.fixture(autouse=True)
def _require_postgres(sync_engine):
    """Skip integration tests when PostgreSQL is unavailable."""


@pytest.fixture(autouse=True)
def _clean_participants(sync_engine):
    """Reset participant rows between integration tests."""
    with sync_engine.connect() as conn:
        conn.execute(text("DELETE FROM scores"))
        conn.execute(text("DELETE FROM participants"))
        conn.commit()
    yield


@pytest.fixture
def shared_faiss_app(app):
    """Point API and worker at the same on-disk FAISS index under data/faiss/."""
    faiss_dir = REPO_ROOT / "data" / "faiss"
    faiss_dir.mkdir(parents=True, exist_ok=True)
    os.environ["FAISS_INDEX_PATH"] = str(faiss_dir / "faiss_index.bin")
    os.environ["EMBEDDING_MAP_PATH"] = str(faiss_dir / "embedding_map.json")
    get_settings.cache_clear()

    matcher = FaceMatcher()
    matcher.load()
    app.state.face_matcher = matcher
    yield app
    matcher.save()


@pytest.fixture
def live_cv_app(shared_faiss_app):
    """FastAPI app with real SCRFD/ArcFace models for registration integration tests."""
    models_dir = REPO_ROOT / "models"
    scrfd = models_dir / "scrfd_10g.onnx"
    arcface = models_dir / "arcface_r100.onnx"
    if not scrfd.exists() or not arcface.exists():
        pytest.skip("Face ONNX models not found in models/ — run download_models.sh on VM")
    shared_faiss_app.state.face_detector = FaceDetector()
    shared_faiss_app.state.face_recognizer = FaceRecognizer()
    return shared_faiss_app


@pytest.fixture
def require_redis():
    if not redis_available():
        pytest.skip("Redis not reachable at REDIS_URL")
