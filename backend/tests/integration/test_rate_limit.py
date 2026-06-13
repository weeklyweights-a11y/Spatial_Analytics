"""Rate limit integration tests."""

import pytest

from backend.tests.conftest import make_face_jpeg


@pytest.mark.asyncio
async def test_register_rate_limit(client, admin_token):
    jpeg = make_face_jpeg()
    last_status = 200
    for i in range(12):
        res = await client.post(
            "/api/v1/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "name": f"User {i}",
                "team_name": "T",
                "track": "ai_ml",
                "consent_confirmed": "true",
            },
            files={"photo": ("face.jpg", jpeg, "image/jpeg")},
        )
        last_status = res.status_code
    assert last_status == 429
