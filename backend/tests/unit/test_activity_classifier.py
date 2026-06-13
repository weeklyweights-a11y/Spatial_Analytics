"""Unit tests for activity_classifier."""

import numpy as np

from backend.core.activity_classifier import ActivityClassifier, _L_WRIST, _R_WRIST, _L_SHOULDER, _R_SHOULDER


def _kp49() -> np.ndarray:
    kp = np.zeros((49, 3), dtype=np.float32)
    kp[:, 2] = 1.0
    return kp


def test_mentoring_zone():
    clf = ActivityClassifier()
    assert clf.classify(1, "mentoring", _kp49()) == "mentoring"


def test_coding_hands_forward():
    clf = ActivityClassifier()
    kp = _kp49()
    kp[_L_SHOULDER, 1] = 100
    kp[_R_SHOULDER, 1] = 100
    kp[_L_WRIST, 1] = 150
    kp[_R_WRIST, 1] = 150
    kp[_L_SHOULDER, 0] = 80
    kp[_R_SHOULDER, 0] = 120
    kp[_L_WRIST, 0] = 90
    kp[_R_WRIST, 0] = 110
    assert clf.classify(1, "coding", kp) == "coding"


def test_idle_hands_in_lap():
    clf = ActivityClassifier()
    kp = _kp49()
    kp[11, 1] = 200
    kp[12, 1] = 200
    kp[_L_WRIST, 1] = 250
    kp[_R_WRIST, 1] = 250
    assert clf.classify(2, "coding", kp) == "idle"
