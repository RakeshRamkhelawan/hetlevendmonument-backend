"""
SP-WE-12: SubagentLoader Echte Singleton (CG-005b)

TDD tests -- RED eerst, dan GREEN na de fix.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

# If another test module replaced the real subagent_loader with a MagicMock,
# force re-import so our singleton tests hit the real code.
if isinstance(sys.modules.get("src.core.agents.subagent_loader"), MagicMock):
    sys.modules.pop("src.core.agents.subagent_loader", None)
    for key in list(sys.modules.keys()):
        if key.startswith(("src.core.agents.subagent_loader", "src.core.agents.workflow_engine")):
            sys.modules.pop(key, None)

import pytest

from src.core.agents.subagent_loader import get_loader, initialize_loader, reset_loader


@pytest.fixture(autouse=True)
def _reset():
    reset_loader()
    yield
    reset_loader()


@pytest.mark.unit
def test_two_calls_return_same_instance() -> None:
    """CG-005b: get_loader() moet altijd dezelfde instantie retourneren."""
    a = get_loader()
    b = get_loader()
    assert a is b, "Twee aanroepen van get_loader() gaven verschillende instanties"


@pytest.mark.unit
def test_initialize_loader_without_force_returns_existing() -> None:
    """initialize_loader() zonder force=True mag bestaande instantie NIET overschrijven."""
    first = get_loader()
    second = initialize_loader()
    assert first is second, "initialize_loader() overschreef bestaande singleton"


@pytest.mark.unit
def test_initialize_loader_with_force_creates_new() -> None:
    """initialize_loader(force=True) MOET een nieuwe instantie aanmaken."""
    first = get_loader()
    second = initialize_loader(force=True)
    assert first is not second, "initialize_loader(force=True) gaf dezelfde instantie terug"


@pytest.mark.unit
def test_reset_then_get_gives_new_instance() -> None:
    """reset_loader() + get_loader() geeft een nieuwe instantie."""
    first = get_loader()
    reset_loader()
    second = get_loader()
    assert first is not second


@pytest.mark.unit
def test_workflow_engine_uses_singleton() -> None:
    """WorkflowEngine.subagent_loader volgt reset -- slaat geen verouderde instantie op."""
    from src.core.agents.workflow_engine import WorkflowEngine

    engine = WorkflowEngine()
    reset_loader()
    singleton_after = get_loader()
    assert engine.subagent_loader is singleton_after, (
        "WorkflowEngine.subagent_loader is een verouderde instantie na reset. "
        "Vervang de instance-attribute door een lazy property."
    )


@pytest.mark.unit
def test_enable_generated_agents_flag_preserved() -> None:
    """ENABLE_GENERATED_AGENTS flag werkt na singleton-refactor."""
    os.environ["ENABLE_GENERATED_AGENTS"] = "false"
    try:
        loader = get_loader()
        assert loader is not None
    finally:
        del os.environ["ENABLE_GENERATED_AGENTS"]
