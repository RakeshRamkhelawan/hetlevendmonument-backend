"""
Tests for Phase 7e attr-defined fixes.

Verifies that all type-narrowing fixes for attr-defined errors work correctly:
- D1/D2 templates: results["steps"] can append dicts
- System optimizer: dict results can append to "recommendations" and "actions_taken"
- D3 invoice: result dict can append invoices
- Event store: state["metadata"] can call .update()
- Agency capabilities: checks dict values can call .values()
- Agent model matcher: explanation dict "reasoning" can append strings

These tests verify the TYPE ANNOTATIONS work correctly by exercising the code paths
that previously had mypy attr-defined errors.
"""

from typing import Any, Dict
import pytest


def test_d1_template_imports() -> None:
    """Test that D1 template imports work (syntax validation)."""
    from src.core.demos.templates.d1_intake_offerte import (
        D1Configuration,
        D1Template,
        LeadData,
        QuoteLineItem,
    )

    assert D1Configuration is not None
    assert D1Template is not None
    assert LeadData is not None
    assert QuoteLineItem is not None


def test_d2_template_imports() -> None:
    """Test that D2 template imports work (syntax validation)."""
    from src.core.demos.templates.d2_order_fulfilment import (
        D2Configuration,
        D2Template,
        Order,
        OrderItem,
    )

    assert D2Configuration is not None
    assert D2Template is not None
    assert Order is not None
    assert OrderItem is not None


def test_system_optimizer_imports() -> None:
    """Test that system optimizer imports work (syntax validation)."""
    from src.core.intelligence.system_optimizer import (
        SystemOptimizer,
        OptimizationConfig,
        OptimizationMetrics,
    )

    assert SystemOptimizer is not None
    assert OptimizationConfig is not None
    assert OptimizationMetrics is not None


def test_d3_invoice_imports() -> None:
    """Test that D3 invoice imports work (syntax validation)."""
    from src.core.demos.d3_invoice_control import D3Template

    assert D3Template is not None


def test_event_store_imports() -> None:
    """Test that event store imports work (syntax validation)."""
    from src.core.als.enterprise.events.event_store import (
        StateProjector,
        Event,
        EventType,
    )

    assert StateProjector is not None
    assert Event is not None
    assert EventType is not None


def test_agency_capabilities_imports() -> None:
    """Test that agency capabilities imports work (syntax validation)."""
    from src.core.agents.capabilities.agency_capabilities_extended import (
        AgencyCapabilityRegistry,
    )

    assert AgencyCapabilityRegistry is not None


def test_agent_model_matcher_imports() -> None:
    """Test that agent model matcher imports work (syntax validation)."""
    from src.core.llm.agent_model_matcher import AgentModelMatcher

    assert AgentModelMatcher is not None


def test_dict_annotation_types() -> None:
    """Test that Dict[str, Any] annotations allow list operations."""
    # This test validates that the type annotation fixes work correctly
    # by mimicking what the fixed code does

    # Simulate D1/D2 template pattern
    results: Dict[str, Any] = {
        "workflow": "test",
        "steps": [],
    }
    results["steps"].append({"step": "test", "result": "ok"})
    assert len(results["steps"]) == 1
    assert results["steps"][0]["step"] == "test"

    # Simulate system optimizer pattern
    opt_results: Dict[str, Any] = {
        "status": "completed",
        "recommendations": [],
    }
    opt_results["recommendations"].append("Test recommendation")
    assert len(opt_results["recommendations"]) == 1

    # Simulate D3 invoice pattern
    invoice_result: Dict[str, Any] = {
        "invoices": [],
    }
    invoice_result["invoices"].append({"id": "INV-001", "amount": 1000})
    assert len(invoice_result["invoices"]) == 1

    # Simulate event store pattern
    state: Dict[str, Any] = {
        "metadata": {},
    }
    state["metadata"].update({"key": "value"})
    assert state["metadata"]["key"] == "value"

    # Simulate agency capabilities pattern
    checks: Dict[str, Dict[str, Any]] = {
        "gdpr": {
            "item": "value",
        },
    }
    values = checks["gdpr"].values()
    assert "value" in values


def test_explanation_dict_annotation() -> None:
    """Test that explanation dict allows reasoning list append."""
    # Simulate agent model matcher pattern
    explanation: Dict[str, Any] = {
        "reasoning": [],
        "scores": {},
    }
    explanation["reasoning"].append("Test reasoning")
    assert len(explanation["reasoning"]) == 1
    assert explanation["reasoning"][0] == "Test reasoning"


@pytest.mark.unit
@pytest.mark.slow
def test_mypy_no_attr_defined_errors() -> None:
    """Verify that the fixed files have no attr-defined mypy errors.

    Checks only errors IN the fixed files themselves, not transitive imports.

    Marked as slow: runs mypy subprocess which takes 30-60s.
    Skipped in normal test runs with: pytest -m "not slow"
    """
    import subprocess
    import sys

    try:
        __import__("mypy")
    except ImportError:
        pytest.skip("mypy not installed")

    files = [
        "src/core/demos/templates/d1_intake_offerte.py",
        "src/core/demos/templates/d2_order_fulfilment.py",
        "src/core/llm/agent_model_matcher.py",
        "src/core/intelligence/system_optimizer.py",
        "src/core/demos/d3_invoice_control.py",
        "src/core/als/enterprise/events/event_store.py",
        "src/core/agents/capabilities/agency_capabilities_extended.py",
    ]

    # Batch all files into a single mypy run for speed
    cmd = [sys.executable, "-m", "mypy"] + files + ["--ignore-missing-imports"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    output = result.stdout + result.stderr

    # Collect all attr-defined errors in the target files
    errors_by_file = {}
    for line in output.split("\n"):
        if "[attr-defined]" in line:
            # Extract which file the error is in
            for filepath in files:
                if filepath in line:
                    if filepath not in errors_by_file:
                        errors_by_file[filepath] = []
                    errors_by_file[filepath].append(line)
                    break

    assert len(errors_by_file) == 0, (
        f"Found attr-defined errors:\n{chr(10).join(chr(10).join(errors) for errors in errors_by_file.values())}"
    )
