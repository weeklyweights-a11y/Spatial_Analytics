"""Auth integration tests."""

import pytest


@pytest.mark.asyncio
async def test_login_valid(client, admin_user):
    username, password = admin_user
    res = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    assert "token" in res.json()["data"]


@pytest.mark.asyncio
async def test_login_invalid(client):
    res = await client.post("/api/v1/auth/login", json={"username": "nope", "password": "wrong"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_participants_unauthorized(client):
    res = await client.get("/api/v1/participants")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_viewer_forbidden_participants(client, admin_user):
    login = await client.post("/api/v1/auth/login", json={"username": "testviewer", "password": "testpass123"})
    token = login.json()["data"]["token"]
    res = await client.get("/api/v1/participants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_viewer_forbidden_register(client, admin_user, sample_face_jpeg):
    login = await client.post("/api/v1/auth/login", json={"username": "testviewer", "password": "testpass123"})
    token = login.json()["data"]["token"]
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "Bob", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_operator_allowed_register(client, admin_user, sample_face_jpeg):
    login = await client.post(
        "/api/v1/auth/login", json={"username": "testoperator", "password": "testpass123"}
    )
    token = login.json()["data"]["token"]
    res = await client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "Operator Reg", "team_name": "T", "track": "ai_ml", "consent_confirmed": "true"},
        files={"photo": ("face.jpg", sample_face_jpeg, "image/jpeg")},
    )
    assert res.status_code == 201
