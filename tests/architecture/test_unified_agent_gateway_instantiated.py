"""GOV-001 / unified-gateway-never-instantiated.

UnifiedAgentGateway was never instantiated anywhere in real agent-execution paths
(base_agent.py, Dramatiq actors, orchestrators) -- only defined and type-hinted in
gateway_adapters.py. Governance is enforced via GovernanceContract directly on
agents instead (see base_agent.py, autonomous_agent.py, chief_orchestrator.py).

Decision (Sprint Dag 1, AUDIT-ARCH-2026-07-02, Groep 1): keep the module but
correct the misleading docstring claim rather than deleting working, unit-tested
code. This test locks that decision in so gateway_adapters.py cannot silently
re-claim "mandatory governance enforcement" without actually being wired in.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ADAPTERS = REPO_ROOT / "src" / "core" / "agents" / "gateway_adapters.py"
UNIFIED_GATEWAY = REPO_ROOT / "src" / "core" / "agents" / "unified_gateway.py"
SRC_ROOT = REPO_ROOT / "src"

NOT_WIRED_MARKER = "NOT WIRED INTO PRODUCTION EXECUTION PATHS"
INSTANTIATION_NEEDLE = "UnifiedAgentGateway("


def test_gateway_adapters_docstring_discloses_it_is_not_wired_in() -> None:
    source = GATEWAY_ADAPTERS.read_text(encoding="utf-8")
    assert NOT_WIRED_MARKER in source, (
        "gateway_adapters.py must explicitly document that UnifiedAgentGateway is "
        "not instantiated in any production execution path -- GOV-001 backlog item."
    )


def test_unified_agent_gateway_is_never_instantiated_outside_its_own_module() -> None:
    """Regression guard: if this ever fails, either wire the gateway in for real
    (and update the docstring + this test), or the finding has resurfaced.

    Text-search rather than AST-parse: this only needs to reject the literal
    call-syntax `UnifiedAgentGateway(`; a full AST walk of ~1700 files is too
    slow for the per-file 60s timeout used elsewhere in this suite.
    """
    offending: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if py_file in (GATEWAY_ADAPTERS, UNIFIED_GATEWAY):
            continue
        source = py_file.read_text(encoding="utf-8", errors="ignore")
        if INSTANTIATION_NEEDLE in source:
            offending.append(str(py_file.relative_to(REPO_ROOT)))

    assert not offending, (
        f"UnifiedAgentGateway is now instantiated outside its own module in: {offending}. "
        "Update gateway_adapters.py's docstring (remove the NOT_WIRED_MARKER note) and "
        "this test to reflect that governance is enforced via the gateway again."
    )
