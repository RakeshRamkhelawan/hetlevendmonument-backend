"""TDD tests for A2.16: corrective_rag_agent.py lazy import."""

import os
import subprocess
import sys


def test_corrective_rag_agent_imports_cleanly() -> None:
    """Module should import without instantiating the agent at module level."""
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

sys.modules.pop("src.core.agents.corrective_rag_agent", None)
sys.modules.pop("src.core.agents.crag_graph", None)

import src.core.agents.corrective_rag_agent as cra

# Check that corrective_rag_agent was NOT instantiated at import time
has_instance = "corrective_rag_agent" in cra.__dict__
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


def test_corrective_rag_agent_factory_works() -> None:
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

sys.modules.pop("src.core.agents.corrective_rag_agent", None)
sys.modules.pop("src.core.agents.crag_graph", None)

from src.core.agents.corrective_rag_agent import get_corrective_rag_agent

agent = get_corrective_rag_agent()
print(f"agent_type={{type(agent).__name__}}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Factory check failed: {result.stdout} {result.stderr}"
    assert "agent_type=CorrectiveRAGAgent" in result.stdout
