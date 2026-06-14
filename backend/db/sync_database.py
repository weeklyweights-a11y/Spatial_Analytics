"""Synchronous SQLAlchemy session for workers (scoring, venue sync)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.db.models import ActivityLog, Score, ScoringConfig, Zone

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def get_sync_engine() -> Engine:
    """Lazy sync engine singleton."""
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.worker_database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


@contextmanager
def sync_session() -> Generator[Session, None, None]:
    """Context manager yielding a sync DB session."""
    get_sync_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_scoring_config_rows(session: Session) -> list[tuple[str, float, int]]:
    """Load scoring_config table rows."""
    rows = session.execute(select(ScoringConfig.activity, ScoringConfig.weight, ScoringConfig.min_dwell_seconds)).all()
    return [(r[0], float(r[1]), int(r[2])) for r in rows]


def load_zone_name_map(session: Session) -> dict[str, uuid.UUID]:
    """Map zone name -> zone UUID."""
    rows = session.execute(select(Zone.name, Zone.id)).all()
    return {name: zone_id for name, zone_id in rows}


def get_score(session: Session, participant_id: uuid.UUID) -> Optional[Score]:
    """Fetch score row for participant."""
    return session.get(Score, participant_id)


def apply_score_update(
    session: Session,
    participant_id: uuid.UUID,
    total_delta: float,
    minute_deltas: dict[str, float],
    last_zone: Optional[str],
    last_activity: Optional[str],
    last_seen_at: Optional[datetime],
    tags: list[str],
) -> None:
    """UPDATE scores row with cycle deltas."""
    score = session.get(Score, participant_id)
    if score is None:
        score = Score(participant_id=participant_id)
        session.add(score)
    score.total_score = float(score.total_score or 0) + total_delta
    for col, delta in minute_deltas.items():
        current = float(getattr(score, col, 0) or 0)
        setattr(score, col, current + delta)
    if last_zone:
        score.last_zone = last_zone
    if last_activity:
        score.last_activity = last_activity
    if last_seen_at:
        score.last_seen_at = last_seen_at
    score.tags = tags


def insert_activity_log(
    session: Session,
    participant_id: uuid.UUID,
    camera_id: str,
    zone_id: uuid.UUID,
    activity: str,
    bbox: Any,
    confidence: Optional[float],
    timestamp: datetime,
) -> None:
    """INSERT one activity_logs row."""
    session.add(
        ActivityLog(
            participant_id=participant_id,
            camera_id=camera_id,
            zone_id=zone_id,
            activity=activity,
            bbox=bbox,
            confidence=confidence,
            timestamp=timestamp,
        )
    )


def update_all_ranks(session: Session) -> None:
    """Recalculate rank by total_score descending."""
    session.execute(
        text(
            """
            WITH ranked AS (
                SELECT participant_id,
                       RANK() OVER (ORDER BY total_score DESC) AS r
                FROM scores
            )
            UPDATE scores s
            SET rank = ranked.r
            FROM ranked
            WHERE s.participant_id = ranked.participant_id
            """
        )
    )
