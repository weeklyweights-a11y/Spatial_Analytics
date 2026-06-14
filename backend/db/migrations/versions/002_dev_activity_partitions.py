"""Dev activity_logs partitions for June 2026 (local/VM testing)."""

from alembic import op

revision = "002_dev_activity_partitions"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # June 13-16 2026 hourly partitions for dev runs before July event day
    for day in (13, 14, 15, 16):
        for hour in range(24):
            start = f"2026-06-{day:02d} {hour:02d}:00:00+00"
            if hour < 23:
                end = f"2026-06-{day:02d} {hour + 1:02d}:00:00+00"
            elif day < 16:
                end = f"2026-06-{day + 1:02d} 00:00:00+00"
            else:
                end = "2026-06-17 00:00:00+00"
            op.execute(
                f"""
                CREATE TABLE IF NOT EXISTS activity_logs_2026_06_{day:02d}_{hour:02d}
                PARTITION OF activity_logs
                FOR VALUES FROM ('{start}') TO ('{end}')
                """
            )


def downgrade() -> None:
    for day in (13, 14, 15, 16):
        for hour in range(24):
            op.execute(f"DROP TABLE IF EXISTS activity_logs_2026_06_{day:02d}_{hour:02d}")
