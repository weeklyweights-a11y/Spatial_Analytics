"""Integration tests require a running PostgreSQL instance."""

import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _require_postgres(sync_engine):
    """Skip integration tests when PostgreSQL is unavailable."""


@pytest.fixture(autouse=True)
def _clean_participants(sync_engine):
    """Reset participant rows between integration tests."""
    with sync_engine.connect() as conn:
        conn.execute(text("DELETE FROM scores"))
        conn.execute(text("DELETE FROM participants"))
        conn.commit()
    yield
