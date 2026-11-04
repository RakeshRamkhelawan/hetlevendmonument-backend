"""TDD tests for A2.17: jwt_handler.py lazy import."""

import os
import subprocess
import sys


def test_jwt_handler_imports_cleanly() -> None:
    """Module should import without instantiating JWTHandler at module level."""
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

# Clear caches
for key in list(sys.modules.keys()):
    if "jwt_handler" in key or "src.core.auth" in key:
        del sys.modules[key]

# Import the module directly via importlib to avoid attribute shadowing
import importlib
mod = importlib.import_module("src.core.auth.jwt_handler")

# Check that jwt_handler was NOT instantiated at import time
# It should be a _LazyProxy, not a JWTHandler instance
proxy = mod.__dict__.get("jwt_handler")
has_instance = type(proxy).__name__ == "JWTHandler"
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


def test_jwt_handler_factory_works() -> None:
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

for key in list(sys.modules.keys()):
    if "jwt_handler" in key or "src.core.auth" in key:
        del sys.modules[key]

from src.core.auth.jwt_handler import get_jwt_handler

handler = get_jwt_handler()
# _LazyProxy overrides __class__ to return JWTHandler once instantiated
print(f"handler_type={{handler.__class__.__name__}}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Factory check failed: {result.stdout} {result.stderr}"
    assert "handler_type=JWTHandler" in result.stdout
