"""Shared test fixtures for the Algorithm Arena test suite."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.base import Base


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite database and return a sync session.

    Suitable for model-level tests that don't need async.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
