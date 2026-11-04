"""
Architecture tests: governance infrastructure wiring gaps.

These tests are RED on commit -- the problems exist in the codebase now.
They become GREEN once the corresponding sprint items are fixed.

TODO(SP-DLP-001): All six findings below must be resolved before the
governance layer can be considered production-ready.

Why: audit findings (GOV-001 through ADR019-001) show that key governance
components are declared but not actually wired into the execution path,
creating silent fail-open behaviour and incomplete compliance evidence.

Stdlib only -- no src imports, no pytest fixtures, no third-party deps.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8-sig", errors="ignore")


# =============================================================================
# GOV-001: Gatekeeper not wired in RouterService factory
# =============================================================================


def test_gov_001_get_router_passes_gatekeeper_to_service() -> None:
    """get_router() must pass a gatekeeper argument to RouterService.

    TODO(SP-DLP-001): wire gatekeeper into get_router() factory so that
    ADR-017 policy enforcement is active for all tenants by default.

    Current state: RouterService accepts gatekeeper= (line ~191) but
    get_router() at line ~1000 constructs it without the argument, meaning
    every router instance silently fails open on all policy checks.

    Fix: add a gatekeeper parameter to get_router() and pass it through to
    RouterService(..., gatekeeper=gatekeeper).
    """
    src = _read("src/core/als/router.py")

    # Isolate the get_router function body (from its def line to the next top-level def)
    match = re.search(
        r"^async def get_router\b.*?(?=^async def |\Z)", src, re.MULTILINE | re.DOTALL
    )
    assert match, "get_router() function not found in src/core/als/router.py"

    func_body = match.group(0)
    assert "gatekeeper" in func_body, (
        "get_router() does not pass 'gatekeeper' to RouterService -- ADR-017 "
        "policy enforcement is permanently disabled for all router instances. "
        "Add gatekeeper parameter to get_router() and wire it into RouterService(). "
        "(SP-DLP-001 / GOV-001)"
    )


# =============================================================================
# GOV-002: Gatekeeper fail-open for all categories
# =============================================================================


def test_gov_002_gatekeeper_does_not_fail_open() -> None:
    """_check_gatekeeper() must not silently fail open on errors.

    TODO(SP-DLP-001): replace the fail-open exception handler in
    _check_gatekeeper() with a configurable fail-closed policy so that
    gatekeeper errors block execution in production environments.

    Current state: the comment 'fail open for availability' on line ~289
    documents an intentional fail-open: any gatekeeper exception is swallowed
    and the task proceeds unchecked. This is a CRITICAL safety gap.

    Fix: introduce a GATEKEEPER_FAIL_OPEN env/config flag (default False in
    prod) and raise GatekeeperRoutingError when the flag is False.
    """
    src = _read("src/core/als/router.py")

    assert "fail open" not in src, (
        "'fail open' comment found in src/core/als/router.py -- gatekeeper "
        "exceptions are silently swallowed, bypassing ADR-017 policy enforcement "
        "for all tenants. Replace with a configurable fail-closed policy. "
        "(SP-DLP-001 / GOV-002)"
    )


# =============================================================================
# GOV-003: ToolBroker in base_agent without HITLStore
# =============================================================================


def test_gov_003_create_tool_broker_wires_hitl_store() -> None:
    """_create_tool_broker() must pass a hitl_store to ToolBrokerService.

    TODO(SP-DLP-001): add HITLStore wiring to base_agent._create_tool_broker()
    so that human-in-the-loop escalation is reachable from all agents by default.

    Current state: _create_tool_broker() creates ToolBrokerService without
    a hitl_store argument, so HITL escalation silently falls back to no-op
    for every agent that uses the base class broker.

    Fix: inject HITLStore via base_agent constructor and pass it as
    hitl_store=self._hitl_store to ToolBrokerService().
    """
    src = _read("src/core/agents/base_agent.py")

    # Locate the 20 lines surrounding _create_tool_broker
    lines = src.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if "_create_tool_broker" in ln and "def " in ln),
        None,
    )
    assert start is not None, "_create_tool_broker not found in src/core/agents/base_agent.py"

    window = "\n".join(lines[start : start + 20])
    assert "hitl_store" in window, (
        "_create_tool_broker() does not wire 'hitl_store' into ToolBrokerService -- "
        "HITL escalation is unreachable for all base-class agents. "
        "Inject HITLStore in BaseAgent.__init__() and pass it through. "
        "(SP-DLP-001 / GOV-003)"
    )


# =============================================================================
# EU-AI-002: AIActBanner not mounted in App.tsx
# =============================================================================


# =============================================================================
# EU-AI-004: QualityGate checks return WARNING only (no implementations)
# =============================================================================


def test_eu_ai_004_quality_gate_has_risk_classification_check() -> None:
    """quality_management.py must define _check_risk_classification().

    TODO(SP-DLP-001): implement _check_risk_classification() in
    src/core/governance/quality_management.py so that the EU AI Act risk
    classification gate produces real verdicts instead of stub WARNINGs.

    Current state: the method is not defined, meaning QualityGate.run_checks()
    either skips risk classification entirely or delegates to a no-op stub
    that always returns WARNING -- neither satisfies the AI Act obligation.

    Fix: implement _check_risk_classification() to evaluate the agent's
    risk category against the registered autonomy ladder (ADR-031).
    """
    src = _read("src/core/governance/quality_management.py")

    assert "_check_risk_classification" in src, (
        "'_check_risk_classification' not defined in "
        "src/core/governance/quality_management.py -- EU AI Act risk "
        "classification gate is unimplemented; all checks return WARNING. "
        "Implement the method using the ADR-031 autonomy ladder. "
        "(SP-DLP-001 / EU-AI-004)"
    )


# =============================================================================
# ADR019-001: AuditLog model missing hash chain fields
# =============================================================================


def test_adr019_001_audit_log_model_has_hash_chain_fields() -> None:
    """AuditLog class must declare audit_hash and previous_hash fields.

    TODO(SP-DLP-001): add audit_hash and previous_hash columns to the
    AuditLog model (not only to ToolAuditLog) so that the primary audit
    trail also satisfies ADR-019 hash chain requirements.

    Current state: AuditLog (__tablename__ = 'audit_logs') does not declare
    audit_hash or previous_hash. ToolAuditLog has them but that is a
    separate model for tool executions only. The primary AuditLog, which
    records all governance events, is not tamper-evident.

    Fix: add the two mapped_column fields to AuditLog and create an Alembic
    migration. Follow the pattern already used in ToolAuditLog.
    """
    src = _read("src/core/governance/models.py")

    # Isolate the AuditLog class body -- from its class line to the next class definition
    match = re.search(
        r"^class AuditLog\b.*?(?=^class |\Z)",
        src,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "AuditLog class not found in src/core/governance/models.py"

    audit_log_body = match.group(0)
    assert "audit_hash" in audit_log_body, (
        "AuditLog class in src/core/governance/models.py has no 'audit_hash' field -- "
        "the primary audit trail is not tamper-evident as required by ADR-019. "
        "Add audit_hash = mapped_column(String(64), nullable=False) and a "
        "corresponding previous_hash column, then generate an Alembic migration. "
        "(SP-DLP-001 / ADR019-001)"
    )
