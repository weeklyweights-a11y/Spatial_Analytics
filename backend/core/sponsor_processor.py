"""Persist sponsor_stream events to PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from backend.core.sponsor_aggregation import (
    HourlyBucket,
    auto_close_visit,
    hour_bucket,
    hourly_to_engagement_row,
    parse_sponsor_event,
    process_entry,
    process_exit,
    should_auto_close,
)
from backend.db.sync_database import (
    close_sponsor_visit,
    count_completed_visits,
    get_open_sponsor_visit,
    get_sponsor_booth_zone_id,
    get_sponsor_by_id,
    insert_sponsor_visit,
    last_activity_in_zone,
    list_open_sponsor_visits,
    upsert_sponsor_engagement,
)


def _merge_into_store(
    store: dict[tuple[uuid.UUID, datetime], HourlyBucket],
    sponsor_id: uuid.UUID,
    bucket: HourlyBucket,
    ts: datetime,
) -> None:
    hb = hour_bucket(ts)
    key = (sponsor_id, hb)
    if key not in store:
        store[key] = HourlyBucket()
    target = store[key]
    target.entries += bucket.entries
    target.unique_participants |= bucket.unique_participants
    target.visitors_in_hour |= bucket.visitors_in_hour
    target.dwell_seconds.extend(bucket.dwell_seconds)
    for pid, count in bucket.participant_entry_counts.items():
        target.participant_entry_counts[pid] = target.participant_entry_counts.get(pid, 0) + count


def _persist_hourly_engagement(
    session: Session,
    hourly: dict[tuple[uuid.UUID, datetime], HourlyBucket],
) -> None:
    for (sponsor_id, hb), bucket in hourly.items():
        row = hourly_to_engagement_row(bucket)
        upsert_sponsor_engagement(session, sponsor_id, hb, **row)


def _auto_close_open_visits(
    session: Session,
    now: datetime,
    hourly: dict[tuple[uuid.UUID, datetime], HourlyBucket],
) -> None:
    """Close visits with no booth activity for 30+ minutes."""
    for visit in list_open_sponsor_visits(session):
        zone_id = get_sponsor_booth_zone_id(session, visit.sponsor_id)
        last_act = last_activity_in_zone(session, visit.participant_id, zone_id) if zone_id else None
        if not should_auto_close(visit.entered_at, last_act, now):
            continue
        sponsor = get_sponsor_by_id(session, visit.sponsor_id)
        sponsor_name = sponsor.name if sponsor else str(visit.sponsor_id)
        payload, bucket = auto_close_visit(
            visit.participant_id,
            visit.sponsor_id,
            sponsor_name,
            visit.entered_at,
            now,
            visit.visit_number,
        )
        close_sponsor_visit(session, visit, payload["exited_at"], payload["dwell_seconds"])
        _merge_into_store(hourly, visit.sponsor_id, bucket, now)


def process_sponsor_events(session: Session, events: list[dict[str, Any]]) -> int:
    """Apply sponsor stream events and auto-close sweep; return events processed."""
    now = datetime.now(timezone.utc)
    hourly: dict[tuple[uuid.UUID, datetime], HourlyBucket] = {}
    open_ids: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    processed = 0

    for raw in events:
        try:
            event = parse_sponsor_event(raw)
        except (KeyError, ValueError) as exc:
            logger.error(f"Invalid sponsor event skipped: {exc}")
            continue

        if event.event_type == "sponsor_entry":
            visit_number = count_completed_visits(session, event.participant_id, event.sponsor_id) + 1
            payload, bucket = process_entry(event, open_ids, visit_number)
            insert_sponsor_visit(
                session,
                payload["participant_id"],
                payload["sponsor_id"],
                payload["entered_at"],
                payload["visit_number"],
            )
            _merge_into_store(hourly, event.sponsor_id, bucket, event.timestamp)
            processed += 1
        elif event.event_type == "sponsor_exit":
            open_visit = get_open_sponsor_visit(session, event.participant_id, event.sponsor_id)
            if open_visit is None:
                logger.warning(
                    "Sponsor exit without open visit: participant={}, sponsor={}",
                    event.participant_id,
                    event.sponsor_name,
                )
                continue
            close_payload, bucket = process_exit(event, open_visit.entered_at, open_visit.visit_number)
            close_sponsor_visit(
                session,
                open_visit,
                close_payload["exited_at"],
                close_payload["dwell_seconds"],
            )
            _merge_into_store(hourly, event.sponsor_id, bucket, event.timestamp)
            processed += 1

    _persist_hourly_engagement(session, hourly)
    _auto_close_open_visits(session, now, hourly)
    _persist_hourly_engagement(session, hourly)
    return processed
