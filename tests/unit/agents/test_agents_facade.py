"""Tests for src/core/agents/api.py facade (ADR-034 SP-AGT-001 Dag 1)."""

import importlib
import inspect
from pathlib import Path

import pytest


@pytest.mark.unit
def test_agents_api_module_importable() -> None:
    """src/core/agents/api.py moet importeerbaar zijn als module."""
    spec = importlib.util.find_spec("src.core.agents.api")
    assert spec is not None, "src/core/agents/api.py bestaat niet"


@pytest.mark.unit
def test_facade_exports_iagent_runtime() -> None:
    from src.core.agents import api

    assert hasattr(api, "IAgentRuntime"), "IAgentRuntime niet geexporteerd vanuit facade"


@pytest.mark.unit
def test_facade_exports_get_agent_runtime() -> None:
    from src.core.agents import api

    assert hasattr(api, "get_agent_runtime"), "get_agent_runtime niet geexporteerd vanuit facade"


@pytest.mark.unit
def test_facade_max_80_lines() -> None:
    content = Path("src/core/agents/api.py").read_text(encoding="utf-8")
    lines = [
        line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    assert len(lines) <= 80, f"Facade heeft {len(lines)} niet-lege niet-comment regels (max 80)"


@pytest.mark.unit
def test_iagent_runtime_is_protocol() -> None:
    from src.core.agents.api import IAgentRuntime

    assert inspect.isclass(IAgentRuntime), "IAgentRuntime is geen klasse"
    mro_names = [c.__name__ for c in IAgentRuntime.__mro__]
    assert "Protocol" in mro_names, f"IAgentRuntime erft niet van Protocol. MRO: {mro_names}"


@pytest.mark.unit
def test_iagent_runtime_has_orchestrate() -> None:
    from src.core.agents.api import IAgentRuntime

    assert hasattr(IAgentRuntime, "orchestrate"), "IAgentRuntime.orchestrate() methode ontbreekt"
