"""Concurrent registration tests."""

import asyncio
import threading

import numpy as np
import pytest

from backend.tests.conftest import make_face_jpeg


@pytest.mark.asyncio
async def test_concurrent_register(client, admin_token, app):
    jpeg = make_face_jpeg()

    class UniqueRecognizer:
        _counter = 0
        _lock = threading.Lock()

        def align_face(self, image, landmarks, size=112):
            import cv2 as _cv2

            return _cv2.resize(image, (size, size))

        def embed(self, aligned_face):
            with UniqueRecognizer._lock:
                UniqueRecognizer._counter += 1
                n = UniqueRecognizer._counter
            emb = np.zeros(512, dtype=np.float32)
            emb[n % 512] = 1.0
            return emb

    app.state.face_recognizer = UniqueRecognizer()

    async def register_one(i: int):
        return await client.post(
            "/api/v1/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "name": f"Concurrent {i}",
                "team_name": f"Team {i}",
                "track": "ai_ml",
                "consent_confirmed": "true",
            },
            files={"photo": ("face.jpg", jpeg, "image/jpeg")},
        )

    results = await asyncio.gather(*[register_one(i) for i in range(4)])
    success = [r for r in results if r.status_code == 201]
    assert len(success) == 4
