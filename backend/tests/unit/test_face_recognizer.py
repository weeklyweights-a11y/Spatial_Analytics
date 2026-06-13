"""Face recognizer unit tests."""

import numpy as np

from backend.core.face_recognizer import FaceRecognizer


def test_embed_shape_and_normalized():
    recognizer = FaceRecognizer.__new__(FaceRecognizer)
    aligned = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)

    def fake_run(_self, _outputs, _inputs):
        return [np.random.randn(512).astype(np.float32)]

    recognizer.session = type("S", (), {"run": fake_run, "get_inputs": lambda self: [type("I", (), {"name": "input"})()]})()
    recognizer.input_name = "input"

    emb = recognizer.embed(aligned)
    assert emb.shape == (512,)
    assert abs(np.linalg.norm(emb) - 1.0) < 0.01
