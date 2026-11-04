"""TDD tests for A2.3: copilot_websocket_endpoints must not instantiate WebSocketManager at import time."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def test_copilot_ws_imports_cleanly():
    """RED: importing copilot_websocket_endpoints must not crash when REDIS_URL is unset."""
    env = os.environ.copy()
    env.pop("REDIS_URL", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.core.api.copilot_websocket_endpoints; print('OK')",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    assert "OK" in result.stdout


def test_ws_manager_is_lazy():
    """RED: ws_manager must not be an instance at module level after import."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.core.api.copilot_websocket_endpoints as mod; "
            "print(hasattr(mod, 'ws_manager')); "
            "print(type(mod.__dict__.get('ws_manager', None)).__name__)",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    lines = result.stdout.strip().splitlines()
    # If ws_manager is in __dict__ as a real instance, it's eager
    # After fix, ws_manager should NOT be in __dict__ (only _ws_manager = None)
    has_ws_manager = lines[0] == "True"
    typename = lines[1] if len(lines) > 1 else "unknown"
    # Before fix: has_ws_manager=True, typename=WebSocketManager
    # After fix:  has_ws_manager=False (__getattr__ handles it), typename=NoneType or missing
    if has_ws_manager and typename not in ("NoneType", "type"):
        pytest.fail(
            f"ws_manager is eagerly instantiated as {typename!r}; must be lazy"
        )


import pytest
