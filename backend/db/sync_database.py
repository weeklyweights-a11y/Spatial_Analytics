"""Synchronous SQLAlchemy session for workers (scoring, venue sync)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.db.models import (
    ActivityLog,
    Alert,
    ExportLog,
    Participant,
    ParticipantSponsorVisit,
    Score,
    ScoringConfig,
    Sponsor,
    SponsorEngagement,
    Zone,
)

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


def load_sponsor_name_map(session: Session) -> dict[str, uuid.UUID]:
    """Map sponsor name -> sponsor UUID."""
    rows = session.execute(select(Sponsor.name, Sponsor.id)).all()
    return {name: sid for name, sid in rows}


def get_sponsor_by_id(session: Session, sponsor_id: uuid.UUID) -> Optional[Sponsor]:
    """Fetch sponsor row."""
    return session.get(Sponsor, sponsor_id)


def list_sponsors(session: Session) -> list[Sponsor]:
    """Return all sponsors ordered by name."""
    rows = session.execute(select(Sponsor).order_by(Sponsor.name)).scalars().all()
    return list(rows)


def get_open_sponsor_visit(
    session: Session,
    participant_id: uuid.UUID,
    sponsor_id: uuid.UUID,
) -> Optional[ParticipantSponsorVisit]:
    """Most recent unclosed visit for participant at sponsor."""
    row = session.execute(
        select(ParticipantSponsorVisit)
        .where(
            ParticipantSponsorVisit.participant_id == participant_id,
            ParticipantSponsorVisit.sponsor_id == sponsor_id,
            ParticipantSponsorVisit.exited_at.is_(None),
        )
        .order_by(ParticipantSponsorVisit.entered_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row


def count_completed_visits(
    session: Session,
    participant_id: uuid.UUID,
    sponsor_id: uuid.UUID,
) -> int:
    """Count closed visits for visit_number assignment."""
    from sqlalchemy import func

    val = session.scalar(
        select(func.count())
        .select_from(ParticipantSponsorVisit)
        .where(
            ParticipantSponsorVisit.participant_id == participant_id,
            ParticipantSponsorVisit.sponsor_id == sponsor_id,
            ParticipantSponsorVisit.exited_at.isnot(None),
        )
    )
    return int(val or 0)


def insert_sponsor_visit(
    session: Session,
    participant_id: uuid.UUID,
    sponsor_id: uuid.UUID,
    entered_at: datetime,
    visit_number: int,
) -> ParticipantSponsorVisit:
    """Create open sponsor visit row."""
    visit = ParticipantSponsorVisit(
        participant_id=participant_id,
        sponsor_id=sponsor_id,
        entered_at=entered_at,
        visit_number=visit_number,
    )
    session.add(visit)
    session.flush()
    return visit


def close_sponsor_visit(
    session: Session,
    visit: ParticipantSponsorVisit,
    exited_at: datetime,
    dwell_seconds: int,
) -> None:
    """Close an open visit."""
    visit.exited_at = exited_at
    visit.dwell_seconds = dwell_seconds


def list_open_sponsor_visits(session: Session) -> list[ParticipantSponsorVisit]:
    """All visits without exit timestamp."""
    rows = session.execute(
        select(ParticipantSponsorVisit).where(ParticipantSponsorVisit.exited_at.is_(None))
    ).scalars().all()
    return list(rows)


def last_activity_in_zone(
    session: Session,
    participant_id: uuid.UUID,
    zone_id: uuid.UUID,
) -> Optional[datetime]:
    """Latest activity_log timestamp for participant in zone."""
    row = session.execute(
        select(ActivityLog.timestamp)
        .where(
            ActivityLog.participant_id == participant_id,
            ActivityLog.zone_id == zone_id,
        )
        .order_by(ActivityLog.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row


def get_sponsor_booth_zone_id(session: Session, sponsor_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Return booth zone id for sponsor."""
    sponsor = session.get(Sponsor, sponsor_id)
    return sponsor.booth_zone_id if sponsor else None


def upsert_sponsor_engagement(
    session: Session,
    sponsor_id: uuid.UUID,
    hour_bucket: datetime,
    unique_visitors: int,
    total_visits: int,
    avg_dwell_seconds: float,
    median_dwell_seconds: float,
    return_visitors: int,
    peak_visitors_in_hour: int,
) -> None:
    """Upsert hourly sponsor_engagement row."""
    existing = session.execute(
        select(SponsorEngagement).where(
            SponsorEngagement.sponsor_id == sponsor_id,
            SponsorEngagement.hour_bucket == hour_bucket,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            SponsorEngagement(
                sponsor_id=sponsor_id,
                hour_bucket=hour_bucket,
                unique_visitors=unique_visitors,
                total_visits=total_visits,
                avg_dwell_seconds=avg_dwell_seconds,
                median_dwell_seconds=median_dwell_seconds,
                return_visitors=return_visitors,
                peak_visitors_in_hour=peak_visitors_in_hour,
            )
        )
    else:
        existing.unique_visitors = unique_visitors
        existing.total_visits = total_visits
        existing.avg_dwell_seconds = avg_dwell_seconds
        existing.median_dwell_seconds = median_dwell_seconds
        existing.return_visitors = return_visitors
        existing.peak_visitors_in_hour = peak_visitors_in_hour
    session.flush()


def fetch_sponsor_visits_for_report(
    session: Session,
    sponsor_id: uuid.UUID,
) -> list[ParticipantSponsorVisit]:
    """All closed visits for sponsor report metrics."""
    rows = session.execute(
        select(ParticipantSponsorVisit)
        .where(
            ParticipantSponsorVisit.sponsor_id == sponsor_id,
            ParticipantSponsorVisit.exited_at.isnot(None),
        )
        .order_by(ParticipantSponsorVisit.entered_at)
    ).scalars().all()
    return list(rows)


def fetch_participant_visits(
    session: Session,
    participant_id: uuid.UUID,
) -> list[tuple[ParticipantSponsorVisit, str]]:
    """Sponsor visits for participant with sponsor name."""
    rows = session.execute(
        select(ParticipantSponsorVisit, Sponsor.name)
        .join(Sponsor, Sponsor.id == ParticipantSponsorVisit.sponsor_id)
        .where(ParticipantSponsorVisit.participant_id == participant_id)
        .order_by(ParticipantSponsorVisit.entered_at)
    ).all()
    return list(rows)


def insert_export_log(
    session: Session,
    user_id: uuid.UUID,
    export_type: str,
    anonymized: bool,
) -> uuid.UUID:
    """Create export_log row and return id."""
    row = ExportLog(user_id=user_id, export_type=export_type, anonymized=anonymized)
    session.add(row)
    session.flush()
    return row.id


def update_export_log_count(session: Session, export_id: uuid.UUID, row_count: int) -> None:
    """Update export_log row_count on completion."""
    row = session.get(ExportLog, export_id)
    if row is not None:
        row.row_count = row_count

