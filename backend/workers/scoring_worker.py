"""Scoring worker — consumes activity_stream, flushes scores to PostgreSQL."""

from __future__ import annotations

import json
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.core.sponsor_processor import process_sponsor_events
from backend.core.scoring_engine import (
    ScoreRowSnapshot,
    aggregate_events_by_participant,
    apply_min_dwell,
    assign_tags,
    calculate_period_points,
    load_scoring_config,
    merge_minutes_into_row,
    minute_column_for_activity,
)
from backend.db import redis_sync
from backend.db.partitions import ensure_activity_log_partition
from backend.db.sync_database import (
    apply_score_update,
    get_scoring_config_rows,
    get_score,
    get_sync_engine,
    insert_activity_log,
    load_zone_name_map,
    sync_session,
    update_all_ranks,
)


class ScoringWorker:
    """Periodic flush of Redis activity events into PostgreSQL."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.flush_interval = self.settings.SCORING_FLUSH_INTERVAL
        self._shutdown = False
        self._pending_events: list[dict[str, Any]] = []
        self._pending_last_id: Optional[str] = None
        with sync_session() as session:
            self._config = load_scoring_config(get_scoring_config_rows(session))
        self._start_config_listener()

    def _start_config_listener(self) -> None:
        """Reload scoring weights when config changes."""

        def _listen() -> None:
            r = redis_sync.get_sync_redis()
            pubsub = r.pubsub()
            pubsub.subscribe("scoring_config_updated")
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    with sync_session() as session:
                        self._config = load_scoring_config(get_scoring_config_rows(session))
                    logger.info("Scoring config reloaded from database")
                except Exception as exc:
                    logger.error(f"Scoring config reload failed: {exc}")

        thread = threading.Thread(target=_listen, daemon=True, name="scoring-config")
        thread.start()
        self._engine = get_sync_engine()

    def _handle_sigterm(self, *_args: Any) -> None:
        self._shutdown = True

    def _parse_ts(self, raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.now(timezone.utc)

    def _collect_events(self, last_id: str) -> tuple[list[dict[str, Any]], str]:
        events = redis_sync.read_activity_events(last_id=last_id, count=10000)
        if not events:
            return [], last_id
        new_last = str(events[-1].get("id", last_id))
        return events, new_last

    def _collect_sponsor_events(self, last_id: str) -> tuple[list[dict[str, Any]], str]:
        events = redis_sync.read_sponsor_events(last_id=last_id, count=10000)
        if not events:
            return [], last_id
        new_last = str(events[-1].get("id", last_id))
        return events, new_last

    def _flush_sponsor_stream(self) -> None:
        """Consume sponsor_stream and persist visits + hourly engagement."""
        last_id = redis_sync.get_sponsor_last_id() or "0"
        events, new_last = self._collect_sponsor_events(last_id)
        try:
            with sync_session() as session:
                count = process_sponsor_events(session, events)
            if events:
                redis_sync.set_sponsor_last_id(new_last)
            if count:
                logger.info(f"Sponsor stream flush: events={count}")
        except SQLAlchemyError as exc:
            logger.error(f"Sponsor stream flush failed: {exc}")

    def _flush_once(self) -> None:
        self._flush_sponsor_stream()
        t0 = time.monotonic()
        last_id = redis_sync.get_scoring_last_id() or "0"
        new_events, new_last_id = self._collect_events(last_id)
        if self._pending_events:
            batch = self._pending_events + new_events
            batch_last = self._pending_last_id or new_last_id
        else:
            batch = new_events
            batch_last = new_last_id

        if not batch:
            redis_sync.set_scoring_heartbeat(
                last_flush_at=datetime.now(timezone.utc).isoformat(),
                last_duration_ms=int((time.monotonic() - t0) * 1000),
                events_processed=0,
                status="running",
            )
            return

        minutes_by_pid = aggregate_events_by_participant(batch, self.flush_interval)
        active_count = len(minutes_by_pid)

        with sync_session() as session:
            zone_map = load_zone_name_map(session)

        processed_ids: list[str] = []
        errors = 0

        for pid_str, cycle_minutes in minutes_by_pid.items():
            try:
                pid = uuid.UUID(pid_str)
            except ValueError:
                logger.error(f"Invalid participant_id in stream: {pid_str}")
                errors += 1
                continue

            applied = apply_min_dwell(cycle_minutes, self._config)
            period_points = calculate_period_points(applied, self._config)
            minute_deltas: dict[str, float] = {}
            for activity, mins in applied.items():
                col = minute_column_for_activity(activity)
                if col and mins > 0:
                    minute_deltas[col] = minute_deltas.get(col, 0.0) + mins

            participant_events = [e for e in batch if str(e.get("participant_id")) == pid_str]
            last_ev = participant_events[-1] if participant_events else {}
            last_zone = str(last_ev.get("zone", "")) or None
            last_activity = str(last_ev.get("activity", "")) or None
            last_seen = self._parse_ts(last_ev.get("timestamp"))

            visited = 0
            for ev in participant_events:
                zname = str(ev.get("zone", ""))
                if zname:
                    redis_sync.add_visited_zone(pid_str, zname)
            visited = redis_sync.visited_zone_count(pid_str)

            try:
                with sync_session() as session:
                    score = get_score(session, pid)
                    snapshot = ScoreRowSnapshot(
                        coding_minutes=float(score.coding_minutes if score else 0),
                        collaborating_minutes=float(score.collaborating_minutes if score else 0),
                        mentoring_minutes=float(score.mentoring_minutes if score else 0),
                        presenting_minutes=float(score.presenting_minutes if score else 0),
                        networking_minutes=float(score.networking_minutes if score else 0),
                        helping_minutes=float(score.helping_minutes if score else 0),
                        idle_minutes=float(score.idle_minutes if score else 0),
                    )
                    merge_minutes_into_row(snapshot, applied)
                    tags = assign_tags(snapshot, last_seen, visited)

                    apply_score_update(
                        session,
                        pid,
                        period_points,
                        minute_deltas,
                        last_zone,
                        last_activity,
                        last_seen,
                        tags,
                    )

                    for ev in participant_events:
                        zname = str(ev.get("zone", ""))
                        zone_id = zone_map.get(zname)
                        if zone_id is None:
                            logger.warning(f"Unknown zone name for activity log: {zname}")
                            continue
                        ts = self._parse_ts(ev.get("timestamp"))
                        ensure_activity_log_partition(self._engine, ts)
                        bbox = ev.get("bbox")
                        if isinstance(bbox, str):
                            bbox = json.loads(bbox)
                        conf = ev.get("confidence")
                        if isinstance(conf, str):
                            conf = float(conf)
                        insert_activity_log(
                            session,
                            pid,
                            str(ev.get("camera_id", "")),
                            zone_id,
                            str(ev.get("activity", "idle")),
                            bbox,
                            conf,
                            ts,
                        )

                    session.flush()
                    score_row = get_score(session, pid)
                    total = float(score_row.total_score if score_row else period_points)
                    redis_sync.update_participant_state(
                        pid_str,
                        last_zone or "",
                        last_activity or "",
                        total,
                        last_seen=last_seen.isoformat(),
                    )
                processed_ids.append(pid_str)
            except SQLAlchemyError as exc:
                logger.error(f"Score flush failed for participant {pid_str}: {exc}")
                errors += 1
                continue

        try:
            with sync_session() as session:
                update_all_ranks(session)
                for pid_str in processed_ids:
                    score = get_score(session, uuid.UUID(pid_str))
                    if score:
                        redis_sync.update_leaderboard_sync(pid_str, float(score.total_score))
            redis_sync.set_scoring_last_id(batch_last)
            redis_sync.set_scoring_last_flush_at(datetime.now(timezone.utc).isoformat())
            redis_sync.publish_scores_updated()
            self._pending_events = []
            self._pending_last_id = None
        except Exception as exc:
            logger.error(f"Post-flush Redis/PG commit failed: {exc}")
            self._pending_events = batch
            self._pending_last_id = batch_last
            duration_ms = int((time.monotonic() - t0) * 1000)
            redis_sync.set_scoring_heartbeat(
                last_flush_at=datetime.now(timezone.utc).isoformat(),
                last_duration_ms=duration_ms,
                events_processed=len(batch),
                status="error",
            )
            return

        duration_ms = int((time.monotonic() - t0) * 1000)
        if duration_ms > 5000:
            logger.warning(
                f"Scoring flush took {duration_ms}ms for {active_count} active participants"
            )
        redis_sync.set_scoring_heartbeat(
            last_flush_at=datetime.now(timezone.utc).isoformat(),
            last_duration_ms=duration_ms,
            events_processed=len(batch),
            status="running",
        )
        logger.info(
            f"Scoring flush complete: events={len(batch)} participants={active_count} errors={errors} ms={duration_ms}"
        )

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        logger.info(f"Scoring worker started; flush_interval={self.flush_interval}s")
        self._flush_once()
        while not self._shutdown:
            deadline = time.monotonic() + self.flush_interval
            while time.monotonic() < deadline and not self._shutdown:
                time.sleep(0.5)
            if not self._shutdown:
                self._flush_once()
        logger.info("Scoring worker shutdown complete")


def main() -> None:
    worker = ScoringWorker()
    worker.run()


if __name__ == "__main__":
    main()
