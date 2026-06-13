"""Unit tests for person_detector (mock ONNX when model missing)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.core.person_detector import PersonDetector


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.get_inputs.return_value = [MagicMock(name="images", shape=[1, 3, 640, 640])]
    session.get_outputs.return_value = [MagicMock(name="output0")]
    # Output: batch of 1 det with box+score+minimal keypoints
    det = np.zeros((1, 5 + 49 * 3), dtype=np.float32)
    det[0, :4] = [100, 100, 200, 300]
    det[0, 4] = 0.95
    session.run.return_value = [det.reshape(1, 1, -1)]
    return session


@patch("backend.core.person_detector.ort.InferenceSession")
def test_detect_output_shapes(mock_ort, mock_session, tmp_path):
    mock_ort.return_value = mock_session
    det = PersonDetector(model_path=tmp_path / "fake.onnx")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes, scores, keypoints = det.detect(frame)
    assert boxes.shape[1] == 4
    assert scores.ndim == 1
    assert keypoints.shape[1:] == (49, 3)
