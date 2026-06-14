"""Unit tests for scoring_engine."""

from datetime import datetime, timezone

from backend.core.scoring_engine import (
    ScoreRowSnapshot,
    ScoringWeight,
    aggregate_events_by_participant,
    apply_min_dwell,
    assign_tags,
    build_radar_data,
    calculate_period_points,
    load_scoring_config_from_yaml,
)


def _config(min_dwell_zero: bool = False):
    cfg = load_scoring_config_from_yaml(
        __import__("pathlib").Path(__file__).resolve().parents[3] / "configs" / "scoring.yaml"
    )
    if min_dwell_zero:
        for key in cfg:
            cfg[key] = ScoringWeight(cfg[key].activity, cfg[key].weight, 0)
    return cfg


def test_sixty_coding_events_one_point():
    events = [{"participant_id": "a", "activity": "coding"} for _ in range(60)]
    minutes = aggregate_events_by_participant(events, flush_interval_seconds=60)
    applied = apply_min_dwell(minutes["a"], _config(min_dwell_zero=True))
    points = calculate_period_points(applied, _config(min_dwell_zero=True))
    assert applied["coding"] == 1.0
    assert points == 1.0


def test_sixty_mentoring_events_two_points():
    events = [{"participant_id": "a", "activity": "mentoring"} for _ in range(60)]
    minutes = aggregate_events_by_participant(events, flush_interval_seconds=60)
    applied = apply_min_dwell(minutes["a"], _config(min_dwell_zero=True))
    points = calculate_period_points(applied, _config(min_dwell_zero=True))
    assert applied["mentoring"] == 1.0
    assert points == 2.0


def test_mixed_coding_and_mentoring():
    events = (
        [{"participant_id": "a", "activity": "coding"} for _ in range(30)]
        + [{"participant_id": "a", "activity": "mentoring"} for _ in range(30)]
    )
    minutes = aggregate_events_by_participant(events, flush_interval_seconds=60)
    applied = apply_min_dwell(minutes["a"], _config(min_dwell_zero=True))
    points = calculate_period_points(applied, _config(min_dwell_zero=True))
    assert abs(applied["coding"] - 0.5) < 0.01
    assert abs(applied["mentoring"] - 0.5) < 0.01
    assert abs(points - 1.5) < 0.01


def test_min_dwell_skips_short_activity():
    events = [{"participant_id": "a", "activity": "mentoring"} for _ in range(1)]
    minutes = aggregate_events_by_participant(events, flush_interval_seconds=60)
    applied = apply_min_dwell(minutes["a"], _config())
    assert applied.get("mentoring", 0) == 0.0


def test_builder_tag():
    row = ScoreRowSnapshot(coding_minutes=60, collaborating_minutes=20)
    tags = assign_tags(row, datetime.now(timezone.utc), 0)
    assert "Builder" in tags


def test_mentor_tag():
    row = ScoreRowSnapshot(coding_minutes=10, mentoring_minutes=20, helping_minutes=5)
    tags = assign_tags(row, datetime.now(timezone.utc), 0)
    assert "Mentor" in tags


def test_night_owl_tag():
    row = ScoreRowSnapshot(coding_minutes=10)
    ts = datetime(2026, 7, 15, 3, 30, tzinfo=timezone.utc)
    tags = assign_tags(row, ts, 0)
    assert "Night Owl" in tags


def test_no_night_owl_afternoon():
    row = ScoreRowSnapshot(coding_minutes=10)
    ts = datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc)
    tags = assign_tags(row, ts, 0)
    assert "Night Owl" not in tags


def test_radar_five_axes():
    data = build_radar_data({"coding": 30, "collaborating": 20, "mentoring": 10, "presenting": 5, "networking": 5})
    assert len(data) == 5
    assert abs(sum(d["value"] for d in data) - 1.0) < 0.01
