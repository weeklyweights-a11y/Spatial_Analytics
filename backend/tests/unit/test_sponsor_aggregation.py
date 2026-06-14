"""Unit tests for sponsor aggregation logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.core.sponsor_aggregation import (
    HourlyBucket,
    auto_close_visit,
    compute_report_metrics,
    hourly_to_engagement_row,
    merge_hourly_buckets,
    process_entry,
    process_exit,
    should_auto_close,
)


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 13, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def sponsor_id() -> uuid.UUID:
    return uuid.uuid4()


def test_five_entries_and_exits_metrics(sponsor_id: uuid.UUID) -> None:
    """Five entry + five exit events yield five unique visitors and visits."""
    hourly: dict[datetime, HourlyBucket] = {}
    participants = [uuid.uuid4() for _ in range(5)]
    open_visits: dict[tuple[uuid.UUID, uuid.UUID], int] = {}

    for i, pid in enumerate(participants):
        entry_event = type(
            "E",
            (),
            {
                "participant_id": pid,
                "sponsor_id": sponsor_id,
                "timestamp": _ts(14, i * 5),
            },
        )()
        payload, bucket = process_entry(entry_event, open_visits, visit_number=1)
        merge_hourly_buckets(hourly, bucket, entry_event.timestamp)

        exit_event = type(
            "E",
            (),
            {
                "participant_id": pid,
                "sponsor_id": sponsor_id,
                "timestamp": _ts(14, i * 5 + 3),
            },
        )()
        _close_payload, exit_bucket = process_exit(exit_event, payload["entered_at"], 1)
        merge_hourly_buckets(hourly, exit_bucket, exit_event.timestamp)

    closed = [{"participant_id": pid, "dwell_seconds": 180} for pid in participants]
    metrics = compute_report_metrics(closed, [])
    assert metrics["unique_visitors"] == 5
    assert metrics["total_visits"] == 5
    assert metrics["avg_dwell_seconds"] == 180

    hour_key = _ts(14)
    row = hourly_to_engagement_row(hourly[hour_key])
    assert row["unique_visitors"] == 5
    assert row["total_visits"] == 5


def test_return_visitors_same_participant(sponsor_id: uuid.UUID) -> None:
    """Three entries from same participant counts as one return visitor."""
    pid = uuid.uuid4()
    bucket = HourlyBucket()
    for _ in range(3):
        bucket.entries += 1
        bucket.unique_participants.add(pid)
        bucket.participant_entry_counts[pid] = bucket.participant_entry_counts.get(pid, 0) + 1
        bucket.dwell_seconds.append(120)

    row = hourly_to_engagement_row(bucket)
    assert row["return_visitors"] == 1
    assert row["total_visits"] == 3

    visits = [
        {"participant_id": pid, "dwell_seconds": 120},
        {"participant_id": pid, "dwell_seconds": 120},
        {"participant_id": pid, "dwell_seconds": 120},
    ]
    metrics = compute_report_metrics(visits, [])
    assert metrics["unique_visitors"] == 1
    assert metrics["total_visits"] == 3
    assert metrics["return_visitors"] == 1


def test_auto_close_after_thirty_minutes(sponsor_id: uuid.UUID) -> None:
    """Entry without exit auto-closes after 30 min without zone activity."""
    pid = uuid.uuid4()
    entered = _ts(10, 0)
    now = _ts(10, 35)
    assert should_auto_close(entered, last_zone_activity=None, now=now) is True
    assert should_auto_close(entered, last_zone_activity=_ts(10, 20), now=now) is False

    payload, bucket = auto_close_visit(
        pid,
        sponsor_id,
        "Lovable",
        entered,
        now,
        visit_number=1,
    )
    assert payload["dwell_seconds"] == 35 * 60
    assert payload["auto_closed"] is True
    assert len(bucket.dwell_seconds) == 1
