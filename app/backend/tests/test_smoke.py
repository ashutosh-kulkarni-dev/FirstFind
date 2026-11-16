"""Runs the two end-to-end smoke scripts as part of the test suite.

Each script seeds its own throwaway database and walks the app through real
requests (sign-up, search, reviews, lists, chat, rate limits). They run in a
separate process because they configure the database before importing the app.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("script", ["flows.py", "endpoints.py"])
def test_smoke_script(script):
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "PYTHONIOENCODING": "utf-8",
           "HUGGINGFACE_TOKEN": "", "GROQ_API_KEY": "", "ENVIRONMENT": "development"}
    env.pop("DATABASE_URL", None)          # the script sets its own
    run = subprocess.run([sys.executable, str(BACKEND / "tests" / "smoke" / script)],
                         cwd=BACKEND, env=env, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=600)
    tail = "\n".join((run.stdout[-3000:], run.stderr[-3000:]))
    assert run.returncode == 0, f"{script} failed:\n{tail}"
