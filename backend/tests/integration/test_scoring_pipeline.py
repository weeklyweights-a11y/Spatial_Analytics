"""Integration tests for scoring pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.core.scoring_engine import ScoringWeight
from backend.db.models import Participant, Score, Zone
from backend.db.sync_database import sync_session
from backend.workers.scoring_worker import ScoringWorker


@pytest.fixture
def test_zone(sync_engine):
    zone_id = uuid.uuid4()
    with Session(sync_engine) as session:
        session.add(
            Zone(
                id=zone_id,
                name="Pipeline Test Zone",
                zone_type="coding",
                camera_id="CAM-01",
                polygon_coords={"points": [[0, 0], [1, 0], [1, 1]]},
                floor=0,
                capacity=50,
            )
        )
        session.commit()
    return zone_id


def test_scoring_flush_updates_total_score(test_zone, sync_engine):
    pid = uuid.uuid4()
    with Session(sync_engine) as session:
        session.add(
            Participant(id=pid, name="Pipe Test", team_name="T", track="ai_ml")
        )
        session.add(Score(participant_id=pid))
        session.commit()

    events = [
        {
            "id": f"1-{i}",
            "participant_id": str(pid),
            "camera_id": "CAM-01",
            "zone": "Pipeline Test Zone",
            "activity": "coding",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bbox": [0, 0, 10, 10],
            "confidence": 0.9,
        }
        for i in range(60)
    ]

    with patch("backend.workers.scoring_worker.redis_sync.read_activity_events", return_value=events), patch(
        "backend.workers.scoring_worker.redis_sync.get_scoring_last_id", return_value="0"
    ), patch("backend.workers.scoring_worker.redis_sync.set_scoring_last_id"), patch(
        "backend.workers.scoring_worker.redis_sync.set_scoring_last_flush_at"
    ), patch(
        "backend.workers.scoring_worker.redis_sync.set_scoring_heartbeat"
    ), patch(
        "backend.workers.scoring_worker.redis_sync.publish_scores_updated"
    ), patch(
        "backend.workers.scoring_worker.redis_sync.update_participant_state"
    ), patch(
        "backend.workers.scoring_worker.redis_sync.update_leaderboard_sync"
    ), patch(
        "backend.workers.scoring_worker.redis_sync.add_visited_zone"
    ), patch(
        "backend.workers.scoring_worker.redis_sync.visited_zone_count", return_value=1
    ):
        worker = ScoringWorker()
        worker._config = {
            key: ScoringWeight(cfg.activity, cfg.weight, 0) for key, cfg in worker._config.items()
        }
        worker._flush_once()

    with sync_session() as session:
        score = session.get(Score, pid)
        assert score is not None
        assert score.total_score > 0
