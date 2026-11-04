"""E2E integration test for AgentRunner via subprocess."""

import subprocess
import sys
import os
import pytest


def test_agent_runner_imports() -> None:
    """Verify AgentRunner can be imported in a clean process."""
    code = """
import sys, os
sys.path.insert(0, os.getcwd())
from src.core.agent_runner import AgentRunner
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=10,
        cwd=os.getcwd(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
    assert b"OK" in result.stdout


def test_signal_bus_imports() -> None:
    code = """
import sys, os
sys.path.insert(0, os.getcwd())
from src.core.als.infrastructure.signal_bus import SignalBus, Signal
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=10,
        cwd=os.getcwd(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
    assert b"OK" in result.stdout
