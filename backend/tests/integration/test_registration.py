"""Registration integration tests."""

import uuid

import cv2
import numpy as np
import pytest

from backend.core.face_detector import Face
from backend.tests.conftest import make_face_jpeg


@pytest.mark.asyncio
async def test_register_success(client, admin_token, sample_face_jpeg):
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "name": "Alice Test",
            "team_name": "Team Alpha",
            "track": "ai_ml",
            "consent_confirmed": "true",
        },
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["name"] == "Alice Test"
    assert "embedding_id" in data


@pytest.mark.asyncio
async def test_register_no_auth(client, sample_face_jpeg):
    res = await client.post(
        "/api/v1/register",
        data={"name": "Bob", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_register_no_face(client, admin_token, app):
    class EmptyDetector:
        def detect(self, image, threshold=0.5):
            return []

    app.state.face_detector = EmptyDetector()
    jpeg = make_face_jpeg()
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "Bob", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", jpeg, "image/jpeg")},
    )
    assert res.status_code == 400
    assert "No face detected in photo" in res.json()["error"]


@pytest.mark.asyncio
async def test_register_multiple_faces(client, admin_token, app, sample_face_jpeg):
    class MultiDetector:
        def detect(self, image, threshold=0.5):
            f = Face(
                bbox=np.zeros(4, dtype=np.float32),
                confidence=0.9,
                landmarks=np.zeros((5, 2), dtype=np.float32),
            )
            return [f, f]

    app.state.face_detector = MultiDetector()
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "Bob", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 400
    assert "Multiple faces detected" in res.json()["error"]


@pytest.mark.asyncio
async def test_register_no_consent(client, admin_token, sample_face_jpeg):
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "Bob", "team_name": "T", "track": "ai_ml", "consent_confirmed": "false"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_faiss_persist_after_reload(client, admin_token, sample_face_jpeg, face_matcher, tmp_path):
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "Persist Test", "team_name": "T", "track": "open", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 201
    face_matcher.save()

    from backend.core.face_matcher import FaceMatcher

    reloaded = FaceMatcher()
    reloaded.index_path = face_matcher.index_path
    reloaded.map_path = face_matcher.map_path
    reloaded.load()
    assert reloaded.count() == 1


@pytest.mark.asyncio
async def test_register_duplicate(client, admin_token, sample_face_jpeg, app):
    """Same embedding twice should return 409 with existing name."""

    class FixedRecognizer:
        _emb = np.ones(512, dtype=np.float32)
        _emb /= np.linalg.norm(_emb)

        def align_face(self, image, landmarks, size=112):
            return cv2.resize(image, (size, size))

        def embed(self, aligned_face):
            return self._emb.copy()

    app.state.face_recognizer = FixedRecognizer()
    first = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "Original Name", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "Duplicate Try", "team_name": "T2", "track": "open", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert second.status_code == 409
    assert "Already registered as Original Name" in second.json()["error"]


@pytest.mark.asyncio
async def test_delete_opt_out(client, admin_token, sample_face_jpeg, app, face_matcher):
    """DELETE anonymizes participant and rebuilds FAISS index."""

    class FixedRecognizer:
        _emb = np.full(512, 0.5, dtype=np.float32)
        _emb /= np.linalg.norm(_emb)

        def align_face(self, image, landmarks, size=112):
            import cv2 as _cv2

            return _cv2.resize(image, (size, size))

        def embed(self, aligned_face):
            return self._emb.copy()

    app.state.face_recognizer = FixedRecognizer()
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "To Opt Out", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 201
    participant_id = res.json()["data"]["id"]
    assert face_matcher.count() == 1

    delete = await client.delete(
        f"/api/v1/participants/{participant_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete.status_code == 200
    assert delete.json()["data"]["opted_out"] is True
    assert face_matcher.count() == 0
