"""FastAPI application entry point."""

import asyncio
import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import auth, health, metrics, participants, registration
from backend.config import get_settings
from backend.core.face_detector import FaceDetector
from backend.core.face_matcher import FaceMatcher
from backend.core.face_recognizer import FaceRecognizer
from backend.db.redis_client import close_redis, init_redis
from backend.middleware.logging import RequestLoggingMiddleware
from backend.middleware.rate_limit import limiter
from backend.middleware.security import SecurityHeadersMiddleware

settings = get_settings()


def _configure_logging() -> None:
    """Structured JSON logging to stdout and file."""
    logger.remove()

    def json_sink(message: Any) -> None:
        record = message.record
        payload = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "service": "api",
            "message": record["message"],
        }
        print(json.dumps(payload), file=sys.stdout)

    logger.add(json_sink, level=settings.LOG_LEVEL)
    log_path = Path("/app/logs/spatialscore.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level=settings.LOG_LEVEL,
        rotation="1 day",
        retention="7 days",
        serialize=True,
    )


async def _health_log_loop(app: FastAPI) -> None:
    """Background task logging health every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        logger.info("Health check: all services healthy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load models, Redis, FAISS; shutdown: cleanup."""
    _configure_logging()
    app.state.start_time = time.time()

    Path(settings.EMBEDDING_MAP_PATH).parent.parent.joinpath("faces").mkdir(parents=True, exist_ok=True)
    Path(settings.EMBEDDING_MAP_PATH).parent.mkdir(parents=True, exist_ok=True)

    await init_redis()

    face_matcher = FaceMatcher()
    face_matcher.load()
    app.state.face_matcher = face_matcher

    models_dir = Path(settings.MODELS_DIR)
    if (models_dir / "scrfd_10g.onnx").exists():
        app.state.face_detector = FaceDetector()
        app.state.face_recognizer = FaceRecognizer()
    else:
        logger.warning("Face models not found — registration disabled until models downloaded")
        app.state.face_detector = None
        app.state.face_recognizer = None

    task = asyncio.create_task(_health_log_loop(app))
    yield
    task.cancel()
    await close_redis()


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(title="SpatialScore API", version="1.0.0", lifespan=lifespan)
    app.state.limiter = limiter

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail), "code": "HTTP_ERROR"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation failed",
                "code": "VALIDATION_ERROR",
                "fields": exc.errors(),
            },
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "code": "RATE_LIMIT"},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled error: {error}", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
        )

    app.include_router(auth.router)
    app.include_router(registration.router)
    app.include_router(participants.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    return app


app = create_app()
