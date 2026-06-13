"""Sync Postgres participant name lookup for camera workers."""

from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.db.models import Participant


class ParticipantNameCache:
    """Periodic refresh of participant_id -> display name."""

    def __init__(self, refresh_seconds: float = 60.0) -> None:
        settings = get_settings()
        url = settings.worker_database_url
        self._engine = create_engine(url, pool_pre_ping=True)
        self._session_factory = sessionmaker(self._engine, class_=Session, expire_on_commit=False)
        self._cache: dict[str, str] = {}
        self._refresh_seconds = refresh_seconds
        self._last_refresh = 0.0

    def refresh_if_stale(self) -> None:
        now = time.monotonic()
        if now - self._last_refresh < self._refresh_seconds:
            return
        self.refresh()

    def refresh(self) -> None:
        with self._session_factory() as session:
            rows = session.execute(
                select(Participant.id, Participant.name).where(Participant.opted_out.is_(False))
            ).all()
            self._cache = {str(row[0]): row[1] for row in rows}
        self._last_refresh = time.monotonic()

    def get_name(self, participant_id: Optional[str]) -> Optional[str]:
        if not participant_id:
            return None
        self.refresh_if_stale()
        return self._cache.get(participant_id)

    def close(self) -> None:
        self._engine.dispose()
