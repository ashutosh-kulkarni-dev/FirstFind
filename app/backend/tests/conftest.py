"""Pytest fixtures: throwaway SQLite + TestClient, no external services needed.

Every test starts with empty tables, so tests cannot depend on (or be broken
by) rows another test left behind.
"""
import os
import tempfile

import pytest

# Point at a throwaway file BEFORE `app.main` is imported (it binds the engine
# at import time).
_TMPDIR = tempfile.mkdtemp(prefix="firstfind_tests_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMPDIR}/test.db")
# Dev-mode behaviour so startup checks don't require a 32-char JWT secret.
os.environ.setdefault("ENVIRONMENT", "development")
# Keep CI offline — skip the HF warmup HTTP call during startup.
os.environ.setdefault("HUGGINGFACE_TOKEN", "")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean_database():
    """Empty every table before each test (much faster than rebuilding them)."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture()
def db():
    """A database session, rolled back and closed afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
