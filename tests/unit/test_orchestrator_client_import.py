"""TDD tests for A2.6: orchestrator_client must not instantiate CircuitBreakerRegistry at import."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def test_orchestrator_client_imports_cleanly():
    """RED: importing orchestrator_client must not crash with no env vars."""
    env = os.environ.copy()
    env.pop("REDIS_URL", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.core.agents.ultimate_cva.orchestrator_client; print('OK')",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    assert "OK" in result.stdout


def test_cb_registry_is_lazy():
    """RED: cb_registry must not be a real CircuitBreakerRegistry at import."""
    script = (
        "import src.core.agents.ultimate_cva.orchestrator_client as mod\n"
        "obj = mod.__dict__.get('cb_registry', 'MISSING')\n"
        "if obj == 'MISSING':\n"
        "    print('LAZY')\n"
        "elif obj is None:\n"
        "    print('NoneType')\n"
        "else:\n"
        "    print(type(obj).__name__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    typename = lines[-1] if lines else "unknown"
    if typename not in ("LAZY", "NoneType"):
        pytest.fail(f"cb_registry is eagerly instantiated as {typename!r}; must be lazy")


import pytest
