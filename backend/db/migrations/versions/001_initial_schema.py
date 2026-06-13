"""Initial schema — all tables, partitions, scoring_config seed."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

SCORING_SEED = [
    ("coding", 1.0, 120, "Sitting in coding zone with laptop posture"),
    ("collaborating", 1.5, 120, "Multiple people in proximity in coding zone"),
    ("mentoring", 2.0, 300, "In mentor booth or visiting other teams"),
    ("presenting", 2.0, 60, "On demo stage facing audience"),
    ("networking", 1.2, 120, "In networking lounge or sponsor area"),
    ("helping_others", 1.8, 600, "Detected in another teams coding area"),
    ("sponsor_engagement", 1.0, 120, "Engaged at sponsor booth"),
    ("eating", 0, 0, "In food area"),
    ("resting", 0, 0, "In rest area"),
    ("idle", 0, 0, "Walking without stopping"),
]

# Placeholder event window — replace via new migration before live event
PARTITION_START = "2026-07-15 00:00:00+00"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("team_name", sa.String(255), nullable=False),
        sa.Column("track", sa.String(100), nullable=False),
        sa.Column("skills", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("photo_path", sa.String(500), nullable=True),
        sa.Column("embedding_id", sa.Integer(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("opted_out", sa.Boolean(), server_default="false", nullable=False),
    )

    op.create_table(
        "cameras",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("rtsp_url", sa.String(500), nullable=False),
        sa.Column("camera_type", sa.String(20), nullable=False, server_default="cctv"),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )

    op.create_table(
        "sponsors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tier", sa.String(50), nullable=True),
        sa.Column("booth_zone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
    )

    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("zone_type", sa.String(50), nullable=False),
        sa.Column("camera_id", sa.String(50), nullable=False),
        sa.Column("polygon_coords", postgresql.JSONB(), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("sponsor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["sponsor_id"], ["sponsors.id"]),
    )

    op.create_foreign_key("fk_sponsors_booth_zone", "sponsors", "zones", ["booth_zone_id"], ["id"])

    op.create_table(
        "scores",
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("participants.id"), primary_key=True),
        sa.Column("total_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("coding_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("collaborating_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("mentoring_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("presenting_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("networking_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("helping_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("idle_minutes", sa.Float(), server_default="0", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("last_zone", sa.String(100), nullable=True),
        sa.Column("last_activity", sa.String(50), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_scores_total_score_desc", "scores", [sa.text("total_score DESC")])

    op.create_table(
        "scoring_config",
        sa.Column("activity", sa.String(50), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("min_dwell_seconds", sa.Integer(), server_default="120", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    scoring_table = sa.table(
        "scoring_config",
        sa.column("activity", sa.String),
        sa.column("weight", sa.Float),
        sa.column("min_dwell_seconds", sa.Integer),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        scoring_table,
        [
            {"activity": a, "weight": w, "min_dwell_seconds": m, "description": d}
            for a, w, m, d in SCORING_SEED
        ],
    )

    op.create_table(
        "sponsor_engagement",
        sa.Column("sponsor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sponsors.id"), primary_key=True),
        sa.Column("hour_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("unique_visitors", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_visits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_dwell_seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("return_visitors", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "heatmap_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zone_occupancy", postgresql.JSONB(), nullable=False),
        sa.Column("total_active", sa.Integer(), nullable=True),
        sa.Column("energy_level", sa.Float(), nullable=True),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="users_role_check"),
    )

    # Partitioned activity_logs — 24 hourly partitions for placeholder event day
    op.execute(
        """
        CREATE TABLE activity_logs (
            id BIGSERIAL,
            participant_id UUID NOT NULL REFERENCES participants(id),
            camera_id VARCHAR(50) NOT NULL,
            zone_id UUID NOT NULL REFERENCES zones(id),
            activity VARCHAR(50) NOT NULL,
            bbox JSONB,
            confidence FLOAT,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp)
        """
    )

    for hour in range(24):
        start = f"2026-07-15 {hour:02d}:00:00+00"
        end = f"2026-07-15 {hour + 1:02d}:00:00+00" if hour < 23 else "2026-07-16 00:00:00+00"
        op.execute(
            f"""
            CREATE TABLE activity_logs_2026_07_15_{hour:02d}
            PARTITION OF activity_logs
            FOR VALUES FROM ('{start}') TO ('{end}')
            """
        )

    op.create_index("ix_activity_logs_participant_ts", "activity_logs", ["participant_id", "timestamp"])
    op.create_index("ix_activity_logs_zone_ts", "activity_logs", ["zone_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_activity_logs_zone_ts", table_name="activity_logs")
    op.drop_index("ix_activity_logs_participant_ts", table_name="activity_logs")
    op.drop_table("activity_logs")
    op.drop_table("users")
    op.drop_table("heatmap_snapshots")
    op.drop_table("sponsor_engagement")
    op.drop_table("scoring_config")
    op.drop_index("ix_scores_total_score_desc", table_name="scores")
    op.drop_table("scores")
    op.drop_constraint("fk_sponsors_booth_zone", "sponsors", type_="foreignkey")
    op.drop_table("zones")
    op.drop_table("sponsors")
    op.drop_table("cameras")
    op.drop_table("participants")
