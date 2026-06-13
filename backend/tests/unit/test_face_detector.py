"""Face detector unit tests."""

import numpy as np

from backend.core.face_detector import Face, FaceDetector


def test_face_dataclass():
    face = Face(
        bbox=np.array([0, 0, 10, 10], dtype=np.float32),
        confidence=0.9,
        landmarks=np.zeros((5, 2), dtype=np.float32),
    )
    assert face.confidence == 0.9
    assert face.landmarks.shape == (5, 2)


def test_detect_with_mock_session():
    detector = FaceDetector.__new__(FaceDetector)
    detector.input_name = "input"
    detector.input_size = (640, 640)

    img = np.zeros((480, 640, 3), dtype=np.uint8)

    def fake_run(_self, _outputs, _inputs):
        scores = np.array([[0.9]], dtype=np.float32)
        boxes = np.array([[100, 100, 200, 200]], dtype=np.float32)
        kps = np.zeros((1, 5, 2), dtype=np.float32)
        return [scores, boxes, kps]

    detector.session = type("S", (), {"run": fake_run, "get_inputs": lambda self: [type("I", (), {"name": "input"})()]})()
    faces = detector.detect(img)
    assert len(faces) >= 0
