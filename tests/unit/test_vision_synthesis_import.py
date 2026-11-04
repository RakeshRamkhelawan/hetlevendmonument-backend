"""TDD tests for A2.15: vision_synthesis.py lazy import."""

import os
import subprocess
import sys


def test_vision_synthesis_imports_cleanly() -> None:
    """Module should import without instantiating at module level."""
    env = {
        **os.environ,
        "TESTING": "1",
        "DATABASE_URL": "sqlite+aiosqlite:///test.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "test-secret-key-32-chars-long!!!!!",
        "JWT_SECRET_KEY": "test-jwt-secret-key-32-chars-long!",
    }
    code = f"""
import sys

sys.path.insert(0, {os.getcwd()!r})

sys.modules.pop("src.core.agents.vision_synthesis", None)

import src.core.agents.vision_synthesis as vs

# Check that vision_synthesis was NOT instantiated at import time
has_instance = "vision_synthesis" in vs.__dict__
print(f"has_instance={{has_instance}}")
if has_instance:
    sys.exit(1)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Lazy check failed: {result.stdout} {result.stderr}"


def test_vision_synthesis_factory_works() -> None:
    """Factory should instantiate correctly when called."""
    env = {
        **os.environ,
        "TESTING": "1",
        "DATABASE_URL": "sqlite+aiosqlite:///test.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "test-secret-key-32-chars-long!!!!!",
        "JWT_SECRET_KEY": "test-jwt-secret-key-32-chars-long!",
    }
    code = f"""
import sys

sys.path.insert(0, {os.getcwd()!r})

sys.modules.pop("src.core.agents.vision_synthesis", None)

from src.core.agents.vision_synthesis import get_vision_synthesis

vs = get_vision_synthesis()
print(f"vs_type={{type(vs).__name__}}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Factory check failed: {result.stdout} {result.stderr}"
    assert "vs_type=VisionSynthesis" in result.stdout
