"""Shared helpers for Phase 2 camera pipeline integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import redis

REPO_ROOT = Path(__file__).resolve().parents[3]


def integration_enabled() -> bool:
    """True when full VM integration suite should run."""
    return os.environ.get("RUN_INTEGRATION_TESTS") == "1"


def gpu_pipeline_enabled() -> bool:
    """True when DEIMv2 + live worker tests should run."""
    return integration_enabled() and os.environ.get("DEIMv2_INTEGRATION") == "1"


def skip_reason() -> str:
    return "Set RUN_INTEGRATION_TESTS=1 (and DEIMv2_INTEGRATION=1 for GPU pipeline tests)"


def gpu_skip_reason() -> str:
    return "Set RUN_INTEGRATION_TESTS=1 and DEIMv2_INTEGRATION=1 with models and test video"


def test_video_path() -> Path:
    """Resolve test video from TEST_VIDEO_PATH or test_data/test.mp4."""
    env_path = os.environ.get("TEST_VIDEO_PATH")
    if env_path:
        return Path(env_path)
    return REPO_ROOT / "test_data" / "test.mp4"


def deimv2_model_path() -> Path:
    models_dir = Path(os.environ.get("MODELS_DIR", REPO_ROOT / "models"))
    custom = os.environ.get("DEIMV2_MODEL_PATH")
    if custom:
        return Path(custom)
    return models_dir / "deimv2_s_wholebody49.onnx"


def redis_available() -> bool:
    try:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


def ffmpeg_available() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None


def gpu_prerequisites_met() -> bool:
    return (
        gpu_pipeline_enabled()
        and ffmpeg_available()
        and redis_available()
        and deimv2_model_path().exists()
        and test_video_path().exists()
    )


def read_video_frame(path: Path, frame_index: int = 0) -> np.ndarray:
    """Read a single BGR frame from a video file."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    try:
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"Cannot read frame {frame_index} from {path}")
        return frame
    finally:
        cap.release()


def frame_to_jpeg_bytes(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")
    return buf.tobytes()


def wait_for(
    predicate: Callable[[], bool],
    timeout_seconds: float = 90.0,
    interval_seconds: float = 1.0,
    description: str = "condition",
) -> bool:
    """Poll until predicate is true or timeout."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return False


class ManagedProcess:
    """Start and stop a subprocess safely."""

    def __init__(self, cmd: list[str], env: Optional[dict[str, str]] = None, cwd: Optional[Path] = None) -> None:
        self.cmd = cmd
        self.env = env
        self.cwd = str(cwd or REPO_ROOT)
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.cmd,
            env=self.env,
            cwd=self.cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.proc = None

    def __enter__(self) -> ManagedProcess:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


def build_worker_env() -> dict[str, str]:
    """Environment for camera worker subprocess."""
    env = os.environ.copy()
    env.setdefault("JWT_SECRET", "test-jwt-secret-key-minimum-32-characters-long")
    env.setdefault("PYTHONPATH", str(REPO_ROOT))
    env.setdefault("REDIS_URL", "redis://localhost:6379/0")
    env.setdefault("MODELS_DIR", str(REPO_ROOT / "models"))
    env.setdefault("CONFIGS_DIR", str(REPO_ROOT / "configs"))
    env.setdefault(
        "FAISS_INDEX_PATH",
        str(REPO_ROOT / "data" / "faiss" / "faiss_index.bin"),
    )
    env.setdefault(
        "EMBEDDING_MAP_PATH",
        str(REPO_ROOT / "data" / "faiss" / "embedding_map.json"),
    )
    if "WORKER_DATABASE_URL" not in env:
        db_password = os.environ.get("DB_PASSWORD", "changeme")
        env["WORKER_DATABASE_URL"] = f"postgresql://spatialscore:{db_password}@localhost:5432/spatialscore"
    env["DATABASE_URL"] = env.get(
        "DATABASE_URL",
        env["WORKER_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://"),
    )
    return env


def start_rtmp_simulator(video: Path, camera_id: str = "cam01", host: str = "127.0.0.1") -> ManagedProcess:
    """Launch simulate_streams.py for one camera."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "simulate_streams.py"),
        "--video",
        str(video),
        "--camera-id",
        camera_id,
        "--host",
        host,
    ]
    return ManagedProcess(cmd)


def start_camera_worker(
    camera_id: str = "CAM-01",
    rtsp_url: str = "rtsp://127.0.0.1:8554/cam01",
) -> ManagedProcess:
    """Launch camera worker subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "backend.workers.camera_worker",
        "--camera-id",
        camera_id,
        "--rtsp-url",
        rtsp_url,
    ]
    return ManagedProcess(cmd, env=build_worker_env())
