"""SQLAlchemy 2.0 declarative models for all phases."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for Alembic metadata."""


class Participant(Base):
    """Registered hackathon participant."""

    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    team_name: Mapped[str] = mapped_column(String(255), nullable=False)
    track: Mapped[str] = mapped_column(String(100), nullable=False)
    skills: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    embedding_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    score: Mapped[Optional["Score"]] = relationship(back_populates="participant", uselist=False)


class Score(Base):
    """Current score state per participant."""

    __tablename__ = "scores"

    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), primary_key=True
    )
    total_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    coding_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    collaborating_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    mentoring_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    presenting_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    networking_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    helping_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    idle_minutes: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_zone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_activity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    participant: Mapped["Participant"] = relationship(back_populates="score")


class Zone(Base):
    """Venue zone definition."""

    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(50), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(50), nullable=False)
    polygon_coords: Mapped[dict] = mapped_column(JSONB, nullable=False)
    floor_polygon: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sponsor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sponsors.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Camera(Base):
    """CCTV camera configuration."""

    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rtsp_url: Mapped[str] = mapped_column(String(500), nullable=False)
    camera_type: Mapped[str] = mapped_column(String(20), nullable=False, default="cctv")
    floor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ActivityLog(Base):
    """Partitioned activity log — parent table mapped for ORM; writes use partitions."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    camera_id: Mapped[str] = mapped_column(String(50), nullable=False)
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    activity: Mapped[str] = mapped_column(String(50), nullable=False)
    bbox: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScoringConfig(Base):
    """Activity scoring weights."""

    __tablename__ = "scoring_config"

    activity: Mapped[str] = mapped_column(String(50), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    min_dwell_seconds: Mapped[int] = mapped_column(Integer, default=120, server_default="120")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Sponsor(Base):
    """Event sponsor."""

    __tablename__ = "sponsors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    booth_zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zones.id", use_alter=True, name="fk_sponsors_booth_zone"),
        nullable=True,
    )
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class SponsorEngagement(Base):
    """Hourly sponsor booth engagement aggregates."""

    __tablename__ = "sponsor_engagement"

    sponsor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sponsors.id"), primary_key=True
    )
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    unique_visitors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_visits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    avg_dwell_seconds: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    return_visitors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class HeatmapSnapshot(Base):
    """Periodic heatmap occupancy snapshot."""

    __tablename__ = "heatmap_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    zone_occupancy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_active: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    energy_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Alert(Base):
    """Organizer alert fired by the heatmap worker."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="alerts_severity_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    zone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    floor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    """Dashboard operator account."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="users_role_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
