"""TDD tests for A2.4: ws_dependencies must not instantiate at import time."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def test_ws_dependencies_imports_cleanly():
    """RED: importing ws_dependencies must not crash with no env vars."""
    env = os.environ.copy()
    env.pop("REDIS_URL", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.core.api.v1.focus_builder.ws_dependencies; print('OK')",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    assert "OK" in result.stdout


def test_ws_deps_are_lazy():
    """RED: _WS_MANAGER, _WS_AUTH, _FLOW_VERIFIER must not be real instances at import."""
    script = (
        "import src.core.api.v1.focus_builder.ws_dependencies as mod\n"
        "for name in ('_WS_MANAGER', '_WS_AUTH', '_FLOW_VERIFIER'):\n"
        "    obj = mod.__dict__.get(name, 'MISSING')\n"
        "    if obj == 'MISSING':\n"
        "        print(name, 'LAZY')\n"
        "    elif obj is None:\n"
        "        print(name, 'NoneType')\n"
        "    else:\n"
        "        print(name, type(obj).__name__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    for line in result.stdout.strip().splitlines():
        name, typename = line.rsplit(" ", 1)
        if typename not in ("LAZY", "NoneType"):
            pytest.fail(f"{name} is eagerly instantiated as {typename!r}; must be lazy")


import pytest
