"""Pytest fixtures: ephemeral SQLite + TestClient, no external services needed."""
import os
import tempfile
import pytest

# Isolate every test session from the dev DB by pointing at a throwaway file.
# Must happen before `app.main` imports (it binds the engine at import time).
_TMPDIR = tempfile.mkdtemp(prefix="firstfind_tests_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMPDIR}/test.db")
# Force dev-mode behaviour so startup checks don't require a 32-char JWT secret.
os.environ.setdefault("ENVIRONMENT", "development")
# Keep CI offline — skip the HF warmup HTTP call during startup.
os.environ.setdefault("HUGGINGFACE_TOKEN", "")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import Base, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
