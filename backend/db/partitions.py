"""Runtime activity_logs partition management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine


def partition_table_name(ts: datetime) -> str:
    """Return child partition table name for an hour bucket."""
    ts = ts.astimezone(timezone.utc)
    return f"activity_logs_{ts.year}_{ts.month:02d}_{ts.day:02d}_{ts.hour:02d}"


def ensure_activity_log_partition(engine: Engine, ts: datetime) -> None:
    """Create hourly partition for activity_logs if missing."""
    ts = ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = ts + timedelta(hours=1)
    child = partition_table_name(ts)
    start_iso = ts.isoformat()
    end_iso = end.isoformat()
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {child}
    PARTITION OF activity_logs
    FOR VALUES FROM ('{start_iso}') TO ('{end_iso}')
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
