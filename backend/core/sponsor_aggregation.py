"""Sponsor visit pairing, auto-close, and hourly engagement aggregation."""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger

AUTO_CLOSE_MINUTES = 30
KNOWN_TRACKS = frozenset({"ai_ml", "web3", "devtools"})


@dataclass
class SponsorEvent:
    """Parsed sponsor_stream event."""

    event_type: str
    participant_id: uuid.UUID
    sponsor_id: uuid.UUID
    sponsor_name: str
    camera_id: str
    timestamp: datetime
    stream_id: Optional[str] = None


@dataclass
class HourlyBucket:
    """In-memory hourly rollup for one sponsor."""

    unique_participants: set[uuid.UUID] = field(default_factory=set)
    entries: int = 0
    dwell_seconds: list[int] = field(default_factory=list)
    participant_entry_counts: dict[uuid.UUID, int] = field(default_factory=dict)
    visitors_in_hour: set[uuid.UUID] = field(default_factory=set)


def parse_sponsor_event(raw: dict[str, Any]) -> SponsorEvent:
    """Convert Redis stream dict to SponsorEvent."""
    ts_raw = raw.get("timestamp")
    if isinstance(ts_raw, datetime):
        ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
    elif isinstance(ts_raw, str):
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    else:
        ts = datetime.now(timezone.utc)
    return SponsorEvent(
        event_type=str(raw.get("type", "")),
        participant_id=uuid.UUID(str(raw["participant_id"])),
        sponsor_id=uuid.UUID(str(raw["sponsor_id"])),
        sponsor_name=str(raw.get("sponsor_name", "")),
        camera_id=str(raw.get("camera_id", "")),
        timestamp=ts,
        stream_id=str(raw.get("id")) if raw.get("id") else None,
    )


def hour_bucket(ts: datetime) -> datetime:
    """Truncate timestamp to hour boundary UTC."""
    ts = ts.astimezone(timezone.utc)
    return ts.replace(minute=0, second=0, microsecond=0)


def process_entry(
    event: SponsorEvent,
    open_visit_ids: dict[tuple[uuid.UUID, uuid.UUID], int],
    visit_number: int,
) -> tuple[dict[str, Any], HourlyBucket]:
    """Handle sponsor_entry — returns visit insert payload and hourly delta."""
    key = (event.participant_id, event.sponsor_id)
    bucket = HourlyBucket()
    bucket.entries += 1
    bucket.unique_participants.add(event.participant_id)
    bucket.visitors_in_hour.add(event.participant_id)
    bucket.participant_entry_counts[event.participant_id] = (
        bucket.participant_entry_counts.get(event.participant_id, 0) + 1
    )
    visit_payload = {
        "participant_id": event.participant_id,
        "sponsor_id": event.sponsor_id,
        "entered_at": event.timestamp,
        "visit_number": visit_number,
    }
    open_visit_ids[key] = visit_number
    return visit_payload, bucket


def process_exit(
    event: SponsorEvent,
    entered_at: datetime,
    visit_number: int,
) -> tuple[dict[str, Any], HourlyBucket]:
    """Handle sponsor_exit — returns close payload and hourly delta."""
    dwell = max(0, int((event.timestamp - entered_at).total_seconds()))
    bucket = HourlyBucket()
    bucket.dwell_seconds.append(dwell)
    bucket.unique_participants.add(event.participant_id)
    bucket.visitors_in_hour.add(event.participant_id)
    close_payload = {
        "participant_id": event.participant_id,
        "sponsor_id": event.sponsor_id,
        "entered_at": entered_at,
        "exited_at": event.timestamp,
        "dwell_seconds": dwell,
        "visit_number": visit_number,
    }
    return close_payload, bucket


def should_auto_close(
    entered_at: datetime,
    last_zone_activity: Optional[datetime],
    now: datetime,
    timeout_minutes: int = AUTO_CLOSE_MINUTES,
) -> bool:
    """True when visit exceeded timeout with no booth-zone activity."""
    cutoff = now - timedelta(minutes=timeout_minutes)
    if entered_at > cutoff:
        return False
    if last_zone_activity is not None and last_zone_activity > cutoff:
        return False
    return True


def auto_close_visit(
    participant_id: uuid.UUID,
    sponsor_id: uuid.UUID,
    sponsor_name: str,
    entered_at: datetime,
    closed_at: datetime,
    visit_number: int,
    participant_name: str = "",
) -> tuple[dict[str, Any], HourlyBucket]:
    """Build auto-close payload and hourly bucket contribution."""
    dwell = max(0, int((closed_at - entered_at).total_seconds()))
    bucket = HourlyBucket()
    bucket.dwell_seconds.append(dwell)
    bucket.unique_participants.add(participant_id)
    bucket.visitors_in_hour.add(participant_id)
    if participant_name:
        logger.warning(
            "Unclosed sponsor visit: participant={}, sponsor={}, entered_at={} — auto-closing",
            participant_name,
            sponsor_name,
            entered_at.isoformat(),
        )
    payload = {
        "participant_id": participant_id,
        "sponsor_id": sponsor_id,
        "entered_at": entered_at,
        "exited_at": closed_at,
        "dwell_seconds": dwell,
        "visit_number": visit_number,
        "auto_closed": True,
    }
    return payload, bucket


def merge_hourly_buckets(target: dict[datetime, HourlyBucket], source: HourlyBucket, ts: datetime) -> None:
    """Merge source bucket into target hour key."""
    key = hour_bucket(ts)
    if key not in target:
        target[key] = HourlyBucket()
    bucket = target[key]
    bucket.entries += source.entries
    bucket.unique_participants |= source.unique_participants
    bucket.visitors_in_hour |= source.visitors_in_hour
    bucket.dwell_seconds.extend(source.dwell_seconds)
    for pid, count in source.participant_entry_counts.items():
        bucket.participant_entry_counts[pid] = bucket.participant_entry_counts.get(pid, 0) + count


def hourly_to_engagement_row(bucket: HourlyBucket) -> dict[str, Any]:
    """Convert HourlyBucket to sponsor_engagement upsert fields."""
    dwells = bucket.dwell_seconds
    avg_dwell = float(statistics.mean(dwells)) if dwells else 0.0
    median_dwell = float(statistics.median(dwells)) if dwells else 0.0
    return_visitors = sum(1 for c in bucket.participant_entry_counts.values() if c > 1)
    return {
        "unique_visitors": len(bucket.unique_participants),
        "total_visits": bucket.entries if bucket.entries else len(dwells),
        "avg_dwell_seconds": avg_dwell,
        "median_dwell_seconds": median_dwell,
        "return_visitors": return_visitors,
        "peak_visitors_in_hour": len(bucket.visitors_in_hour),
    }


def compute_report_metrics(
    visits: list[dict[str, Any]],
    hourly_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive Section 3 report metrics from closed visits and hourly engagement."""
    if not visits:
        return {
            "unique_visitors": 0,
            "total_visits": 0,
            "avg_dwell_seconds": 0,
            "median_dwell_seconds": 0,
            "return_visitors": 0,
            "return_rate_pct": 0.0,
            "peak_hour": "00:00",
            "total_dwell_minutes": 0,
        }
    dwells = [int(v["dwell_seconds"]) for v in visits if v.get("dwell_seconds") is not None]
    participants = {v["participant_id"] for v in visits}
    visit_counts: dict[Any, int] = {}
    for v in visits:
        pid = v["participant_id"]
        visit_counts[pid] = visit_counts.get(pid, 0) + 1
    return_visitors = sum(1 for c in visit_counts.values() if c > 1)
    unique = len(participants)
    return_rate = (return_visitors / unique * 100.0) if unique else 0.0
    peak_hour = "00:00"
    if hourly_rows:
        best = max(hourly_rows, key=lambda r: r.get("unique_visitors", 0))
        hb = best.get("hour_bucket")
        if isinstance(hb, datetime):
            peak_hour = hb.astimezone(timezone.utc).strftime("%H:%M")
    total_dwell_minutes = int(sum(dwells) / 60) if dwells else 0
    return {
        "unique_visitors": unique,
        "total_visits": len(visits),
        "avg_dwell_seconds": int(statistics.mean(dwells)) if dwells else 0,
        "median_dwell_seconds": int(statistics.median(dwells)) if dwells else 0,
        "return_visitors": return_visitors,
        "return_rate_pct": round(return_rate, 1),
        "peak_hour": peak_hour,
        "total_dwell_minutes": total_dwell_minutes,
    }


def build_hourly_traffic(hourly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build hourly_traffic with visitors and entries per spec."""
    result: list[dict[str, Any]] = []
    for row in sorted(hourly_rows, key=lambda r: r.get("hour_bucket") or datetime.min.replace(tzinfo=timezone.utc)):
        hb = row.get("hour_bucket")
        if not isinstance(hb, datetime):
            continue
        result.append(
            {
                "hour": hb.astimezone(timezone.utc).strftime("%H:%M"),
                "visitors": int(row.get("unique_visitors", 0)),
                "entries": int(row.get("total_visits", 0)),
            }
        )
    return result


def normalize_track(track: str) -> str:
    """Map participant track to report bucket including other."""
    t = (track or "").strip().lower().replace("-", "_").replace(" ", "_")
    if t in KNOWN_TRACKS:
        return t
    return "other"


def floor_key(floor: int) -> str:
    """Map zone floor integer to report key."""
    mapping = {0: "ground", 1: "first", 2: "second"}
    return mapping.get(floor, "other")


def build_visitor_breakdown(
    visits: list[dict[str, Any]],
    participant_meta: dict[uuid.UUID, dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """Build by_track and by_floor breakdown for JSON report."""
    by_track: dict[str, int] = {}
    by_floor: dict[str, int] = {}
    seen: set[uuid.UUID] = set()
    for visit in visits:
        pid = visit["participant_id"]
        if pid in seen:
            continue
        seen.add(pid)
        meta = participant_meta.get(pid, {})
        track = normalize_track(str(meta.get("track", "other")))
        by_track[track] = by_track.get(track, 0) + 1
        floor = floor_key(int(meta.get("floor", 0)))
        by_floor[floor] = by_floor.get(floor, 0) + 1
    return {"by_track": by_track, "by_floor": by_floor}


def build_team_size_breakdown(
    visits: list[dict[str, Any]],
    participant_meta: dict[uuid.UUID, dict[str, Any]],
) -> dict[str, int]:
    """Team-size buckets for PDF pie chart only."""
    buckets: dict[str, int] = {}
    seen: set[uuid.UUID] = set()
    for visit in visits:
        pid = visit["participant_id"]
        if pid in seen:
            continue
        seen.add(pid)
        team = str(participant_meta.get(pid, {}).get("team_name", "Unknown"))
        size_label = "solo" if not team or team.lower() in {"solo", "individual"} else "team"
        buckets[size_label] = buckets.get(size_label, 0) + 1
    return buckets
