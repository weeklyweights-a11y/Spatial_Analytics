"""Phase 4 — alerts table and zones.floor_polygon."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_phase4_alerts_floor_polygon"
down_revision = "002_dev_activity_partitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("zones", sa.Column("floor_polygon", postgresql.JSONB(), nullable=True))

    op.create_table(
        "alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("zone", sa.String(100), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("acknowledged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"]),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="alerts_severity_check",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_alerts_fired_at", "alerts", ["fired_at"], postgresql_ops={"fired_at": "DESC"})
    op.create_index("idx_alerts_severity", "alerts", ["severity", "acknowledged"])


def downgrade() -> None:
    op.drop_index("idx_alerts_severity", table_name="alerts")
    op.drop_index("idx_alerts_fired_at", table_name="alerts")
    op.drop_table("alerts")
    op.drop_column("zones", "floor_polygon")
