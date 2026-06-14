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
from backend.db.models import ActivityLog, Alert, Participant, Score, ScoringConfig, Zone

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


def load_zone_metadata(session: Session) -> list[dict[str, Any]]:
    """Load zone metadata for heatmap snapshots."""
    rows = session.execute(
        select(
            Zone.name,
            Zone.zone_type,
            Zone.floor,
            Zone.capacity,
            Zone.floor_polygon,
        )
    ).all()
    result: list[dict[str, Any]] = []
    for name, zone_type, floor, capacity, floor_polygon in rows:
        result.append(
            {
                "name": name,
                "zone_type": zone_type,
                "floor": floor,
                "capacity": capacity or 50,
                "floor_polygon": floor_polygon,
            }
        )
    return result


def count_registered_participants(session: Session) -> int:
    """Count non-opted-out participants."""
    from sqlalchemy import func

    val = session.scalar(
        select(func.count()).select_from(Participant).where(Participant.opted_out.is_(False))
    )
    return int(val or 0)


def insert_heatmap_snapshot(
    session: Session,
    timestamp: datetime,
    zone_occupancy: dict[str, Any],
    total_active: int,
    energy_level: float,
) -> None:
    """INSERT one heatmap_snapshots row."""
    from backend.db.models import HeatmapSnapshot

    session.add(
        HeatmapSnapshot(
            timestamp=timestamp,
            zone_occupancy=zone_occupancy,
            total_active=total_active,
            energy_level=energy_level,
        )
    )


def insert_alert(
    session: Session,
    rule_name: str,
    severity: str,
    message: str,
    zone: Optional[str],
    floor: Optional[int],
    fired_at: datetime,
) -> uuid.UUID:
    """INSERT alert row and return id."""
    alert = Alert(
        rule_name=rule_name,
        severity=severity,
        message=message,
        zone=zone,
        floor=floor,
        fired_at=fired_at,
    )
    session.add(alert)
    session.flush()
    return alert.id


def count_activity_logs_for_zone(session: Session, zone_id: uuid.UUID) -> int:
    """Count activity_logs referencing a zone."""
    from sqlalchemy import func

    val = session.scalar(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.zone_id == zone_id)
    )
    return int(val or 0)
