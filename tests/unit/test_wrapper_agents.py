"""Unit tests for wrapper agent tenant-bound construction."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

import src.core.agents.wrapper_agents as wrapper_agents_module
from src.core.agents.wrapper_agents import (
    AnalyzerAgentWrapper,
    CVAAgentWrapper,
    ExecutionFeedbackAgentWrapper,
    UltimateCVAAgentWrapper,
    get_wrapped_agent,
)


def _install_stub_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    class_name: str,
) -> type:
    class _StubWrappedAgent:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs
            self.tenant_id = kwargs.get("tenant_id")

    stub_module = ModuleType(module_name)
    setattr(stub_module, class_name, _StubWrappedAgent)
    monkeypatch.setitem(sys.modules, module_name, stub_module)
    return _StubWrappedAgent


def test_get_wrapped_agent_rejects_invalid_tenant_before_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid tenant input should fail closed before any wrapper construction happens."""
    called = False

    class _DummyWrapper:
        def __init__(self, tenant_id: int) -> None:
            nonlocal called
            called = True

    monkeypatch.setattr(wrapper_agents_module, "WRAPPER_MAP", {"Dummy": _DummyWrapper})

    with pytest.raises(ValueError, match="tenant_id"):
        get_wrapped_agent("Dummy", tenant_id=0)

    assert called is False


@pytest.mark.parametrize(
    ("wrapper_class", "module_name", "class_name"),
    [
        (AnalyzerAgentWrapper, "src.core.agents.analyzer_agent", "AnalyzerAgent"),
        (CVAAgentWrapper, "src.core.agents.cva_agent", "CVAAgent"),
        (
            ExecutionFeedbackAgentWrapper,
            "src.core.agents.execution_feedback_agent",
            "ExecutionFeedbackAgent",
        ),
        (UltimateCVAAgentWrapper, "src.core.agents.cva_orchestrator", "UltimateCVAAgent"),
    ],
)
def test_tenant_aware_wrappers_forward_tenant_to_wrapped_agent(
    monkeypatch: pytest.MonkeyPatch,
    wrapper_class: type,
    module_name: str,
    class_name: str,
) -> None:
    """Tenant-aware wrapper construction should propagate tenant context to the inner agent."""
    _install_stub_module(monkeypatch, module_name, class_name)

    wrapper = wrapper_class(tenant_id=4242)

    assert wrapper.tenant_id == 4242
    assert wrapper.wrapped_agent.tenant_id == 4242


def test_direct_wrapper_construction_validates_tenant_before_inner_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct wrapper construction should reject invalid tenant input before inner imports run."""
    called = False

    class _FailIfConstructed:
        def __init__(self, *args, **kwargs) -> None:
            nonlocal called
            called = True

    stub_module = ModuleType("src.core.agents.analyzer_agent")
    setattr(stub_module, "AnalyzerAgent", _FailIfConstructed)
    monkeypatch.setitem(sys.modules, "src.core.agents.analyzer_agent", stub_module)

    with pytest.raises(ValueError, match="tenant_id"):
        AnalyzerAgentWrapper(tenant_id=-1)

    assert called is False


def test_get_wrapped_agent_returns_none_for_workflow_wrapper_without_user_context() -> None:
    """Workflow wrapper factory should fail closed when required user context is absent."""
    assert get_wrapped_agent("WorkflowOrchestratorAgent", tenant_id=10001) is None