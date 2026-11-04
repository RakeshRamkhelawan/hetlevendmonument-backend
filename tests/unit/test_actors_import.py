"""TDD tests for A2.9: actors.py lazy import."""

import os
import subprocess
import sys


def test_actors_imports_cleanly() -> None:
    """Module should import without crashing even if Redis is unavailable."""
    env = {
        **os.environ,
        "TESTING": "1",
        "DATABASE_URL": "sqlite+aiosqlite:///test.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "test-secret-key-32-chars-long!!!!!",
        "JWT_SECRET_KEY": "test-jwt-secret-key-32-chars-long!",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import src.workers.actors"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Import failed: {result.stderr}"
