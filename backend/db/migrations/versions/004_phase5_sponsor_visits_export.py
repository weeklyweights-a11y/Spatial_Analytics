"""Phase 5 — participant_sponsor_visits, export_log, sponsor_engagement columns."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_phase5_sponsor_visits_export"
down_revision = "003_phase4_alerts_floor_polygon"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participant_sponsor_visits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sponsor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dwell_seconds", sa.Integer(), nullable=True),
        sa.Column("visit_number", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["sponsor_id"], ["sponsors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sponsor_visits_participant",
        "participant_sponsor_visits",
        ["participant_id"],
    )
    op.create_index(
        "idx_sponsor_visits_sponsor",
        "participant_sponsor_visits",
        ["sponsor_id", "entered_at"],
    )

    op.add_column(
        "sponsor_engagement",
        sa.Column("median_dwell_seconds", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "sponsor_engagement",
        sa.Column("peak_visitors_in_hour", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "export_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(50), nullable=False),
        sa.Column("anonymized", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("export_log")
    op.drop_column("sponsor_engagement", "peak_visitors_in_hour")
    op.drop_column("sponsor_engagement", "median_dwell_seconds")
    op.drop_index("idx_sponsor_visits_sponsor", table_name="participant_sponsor_visits")
    op.drop_index("idx_sponsor_visits_participant", table_name="participant_sponsor_visits")
    op.drop_table("participant_sponsor_visits")
