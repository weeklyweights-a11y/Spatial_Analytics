"""Admin-only data export endpoints."""

from __future__ import annotations

import csv
import io
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.core.trajectory_export import format_opentraj_header, trajectory_rows_from_logs
from backend.db.database import get_db
from backend.db.models import Participant, Score
from backend.db.sync_database import insert_export_log, sync_session, update_export_log_count
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1/export", tags=["export"])

EXPORT_TIMEOUT_SECONDS = 300
SCORES_COLUMNS = [
    "participant_id",
    "name",
    "team_name",
    "track",
    "total_score",
    "rank",
    "coding_minutes",
    "collaborating_minutes",
    "mentoring_minutes",
    "presenting_minutes",
    "networking_minutes",
    "helping_minutes",
    "idle_minutes",
    "tags",
    "registered_at",
    "last_seen_at",
]


def _export_filename(prefix: str, ext: str) -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"spatialscore_{prefix}_{date_str}.{ext}"


def _cache_headers() -> dict[str, str]:
    return {"Cache-Control": "no-store"}


@router.get("/scores")
@limiter.limit("5/minute")
async def export_scores(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin"])),
) -> StreamingResponse:
    """Export all participant scores as CSV."""
    t0 = time.monotonic()
    logger.info(f"Export started: type=scores, user={user.username}, format=csv")

    export_id: Optional[uuid.UUID] = None
    with sync_session() as session:
        export_id = insert_export_log(session, user.id, "scores", False)

    async def generate() -> AsyncIterator[str]:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(SCORES_COLUMNS)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        row_count = 0
        try:
            stmt = (
                select(Participant, Score)
                .outerjoin(Score, Score.participant_id == Participant.id)
                .where(Participant.opted_out.is_(False))
                .order_by(Participant.registered_at)
            )
            rows = (await db.execute(stmt)).all()
            for participant, score in rows:
                if time.monotonic() - t0 > EXPORT_TIMEOUT_SECONDS:
                    yield "# INCOMPLETE EXPORT\n"
                    return
                s = score
                writer.writerow(
                    [
                        str(participant.id),
                        participant.name,
                        participant.team_name,
                        participant.track,
                        float(s.total_score if s else 0),
                        s.rank if s else "",
                        float(s.coding_minutes if s else 0),
                        float(s.collaborating_minutes if s else 0),
                        float(s.mentoring_minutes if s else 0),
                        float(s.presenting_minutes if s else 0),
                        float(s.networking_minutes if s else 0),
                        float(s.helping_minutes if s else 0),
                        float(s.idle_minutes if s else 0),
                        "|".join(s.tags or []) if s and s.tags else "",
                        participant.registered_at.isoformat() if participant.registered_at else "",
                        s.last_seen_at.isoformat() if s and s.last_seen_at else "",
                    ]
                )
                row_count += 1
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        except Exception as exc:
            logger.error(f"Export failed: type=scores, error={exc}")
            yield "# INCOMPLETE EXPORT\n"
            return

        if export_id:
            with sync_session() as session:
                update_export_log_count(session, export_id, row_count)
        duration = time.monotonic() - t0
        logger.info(f"Export complete: type=scores, rows={row_count}, duration={duration:.1f}s")

    filename = _export_filename("scores", "csv")
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            **_cache_headers(),
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/activity-logs")
@limiter.limit("2/minute")
async def export_activity_logs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin"])),
    participant_id: Optional[UUID] = Query(None),
) -> StreamingResponse:
    """Stream activity logs CSV."""
    t0 = time.monotonic()
    logger.info(f"Export started: type=activity_logs, user={user.username}, format=csv")

    export_id: Optional[uuid.UUID] = None
    with sync_session() as session:
        export_id = insert_export_log(session, user.id, "activity_logs", False)

    async def generate() -> AsyncIterator[str]:
        yield "timestamp,participant_id,name,camera_id,zone,activity,confidence\n"
        row_count = 0
        offset = 0
        batch_size = 1000
        try:
            while True:
                if time.monotonic() - t0 > EXPORT_TIMEOUT_SECONDS:
                    yield "# INCOMPLETE EXPORT\n"
                    return
                params: dict = {"limit": batch_size, "offset": offset}
                where = ""
                if participant_id:
                    where = "WHERE al.participant_id = :pid"
                    params["pid"] = str(participant_id)
                q = text(
                    f"""
                    SELECT al.timestamp, al.participant_id, p.name, al.camera_id,
                           z.name AS zone, al.activity, al.confidence
                    FROM activity_logs al
                    JOIN participants p ON p.id = al.participant_id
                    JOIN zones z ON z.id = al.zone_id
                    {where}
                    ORDER BY al.timestamp
                    LIMIT :limit OFFSET :offset
                    """
                )
                result = await db.execute(q, params)
                rows = result.all()
                if not rows:
                    break
                output = io.StringIO()
                writer = csv.writer(output)
                for row in rows:
                    writer.writerow(
                        [
                            row.timestamp.isoformat() if row.timestamp else "",
                            str(row.participant_id),
                            row.name,
                            row.camera_id,
                            row.zone,
                            row.activity,
                            row.confidence if row.confidence is not None else "",
                        ]
                    )
                    row_count += 1
                yield output.getvalue()
                offset += batch_size
        except Exception as exc:
            logger.error(f"Export failed: type=activity_logs, error={exc}")
            yield "# INCOMPLETE EXPORT\n"
            return

        if export_id:
            with sync_session() as session:
                update_export_log_count(session, export_id, row_count)
        duration = time.monotonic() - t0
        logger.info(f"Export complete: type=activity_logs, rows={row_count}, duration={duration:.1f}s")

    filename = _export_filename("activity_logs", "csv")
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            **_cache_headers(),
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/trajectories")
@limiter.limit("2/minute")
async def export_trajectories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin"])),
    format: str = Query("opentraj", pattern="^(opentraj|json)$"),
    anonymize: bool = Query(False),
) -> StreamingResponse:
    """Export trajectory data in OpenTraj TSV format."""
    t0 = time.monotonic()
    logger.info(
        f"Export started: type=trajectories, user={user.username}, format={format}, anonymize={anonymize}"
    )

    export_id: Optional[uuid.UUID] = None
    with sync_session() as session:
        export_id = insert_export_log(session, user.id, "trajectories", anonymize)

    async def generate() -> AsyncIterator[str]:
        yield format_opentraj_header()
        row_count = 0
        offset = 0
        batch_size = 1000
        frame_id = 1
        try:
            while True:
                if time.monotonic() - t0 > EXPORT_TIMEOUT_SECONDS:
                    yield "# INCOMPLETE EXPORT\n"
                    return
                q = text(
                    """
                    SELECT al.participant_id, al.activity, al.bbox, z.name AS zone_name
                    FROM activity_logs al
                    JOIN zones z ON z.id = al.zone_id
                    ORDER BY al.timestamp
                    LIMIT :limit OFFSET :offset
                    """
                )
                result = await db.execute(q, {"limit": batch_size, "offset": offset})
                rows = result.mappings().all()
                if not rows:
                    break
                chunk = "".join(
                    trajectory_rows_from_logs(
                        [dict(r) for r in rows],
                        anonymize=anonymize,
                        start_frame_id=frame_id,
                    )
                )
                frame_id += len(rows)
                row_count += len(rows)
                yield chunk
                offset += batch_size
        except Exception as exc:
            logger.error(f"Export failed: type=trajectories, error={exc}")
            yield "# INCOMPLETE EXPORT\n"
            return

        if export_id:
            with sync_session() as session:
                update_export_log_count(session, export_id, row_count)
        duration = time.monotonic() - t0
        logger.info(f"Export complete: type=trajectories, rows={row_count}, duration={duration:.1f}s")

    filename = _export_filename("trajectories", "tsv")
    return StreamingResponse(
        generate(),
        media_type="text/tab-separated-values",
        headers={
            **_cache_headers(),
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
