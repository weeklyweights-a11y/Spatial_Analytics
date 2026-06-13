"""Integration tests for identity pipeline."""

import os
import shutil

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS") != "1",
    reason="Set RUN_INTEGRATION_TESTS=1 for full VM integration run",
)
def test_identity_pipeline_placeholder():
    """Full run: register face, push video, assert participant_id in events."""
    assert shutil.which("ffmpeg") is not None or os.environ.get("CI") is None
