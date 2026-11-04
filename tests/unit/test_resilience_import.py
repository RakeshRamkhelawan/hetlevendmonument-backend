"""TDD tests for A2.5: resilience module must not instantiate CircuitBreakerRegistry at import."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def test_resilience_imports_cleanly():
    """RED: importing resilience must not crash with no env vars."""
    env = os.environ.copy()
    env.pop("REDIS_URL", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.core.tool_broker.resilience; print('OK')",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    assert "OK" in result.stdout


def test_circuit_breaker_registry_is_lazy():
    """RED: _circuit_breaker_registry must not be a real instance at import."""
    script = (
        "import src.core.tool_broker.resilience as mod\n"
        "obj = mod.__dict__.get('_circuit_breaker_registry', 'MISSING')\n"
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
    typename = result.stdout.strip()
    if typename not in ("LAZY", "NoneType"):
        pytest.fail(
            f"_circuit_breaker_registry is eagerly instantiated as {typename!r}; must be lazy"
        )


import pytest
