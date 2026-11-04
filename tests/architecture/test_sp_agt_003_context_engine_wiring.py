"""
Architecture invariants: AIContextEngine wired as primary enrichment path in CopilotService.

SP-AGT-003 (ADR-034 §5): IAIContextEngine Protocol in protocols.py, context_engine
parameter in CopilotService.__init__, enrich() called before twin_service.get_profile()
in handle_turn().

Tests must stay GREEN after implementation is in place.
"""

from pathlib import Path


def test_iai_context_engine_protocol_defined_in_protocols() -> None:
    """IAIContextEngine Protocol must be in src/core/copilot/protocols.py -- SP-AGT-003."""
    source = Path("src/core/copilot/protocols.py").read_text(encoding="utf-8")
    assert "class IAIContextEngine(Protocol)" in source, (
        "SP-AGT-003: IAIContextEngine Protocol missing from protocols.py"
    )


def test_copilot_service_has_context_engine_parameter() -> None:
    """CopilotService.__init__ must accept context_engine parameter -- SP-AGT-003."""
    source = Path("src/core/copilot/service.py").read_text(encoding="utf-8")
    assert "context_engine: IAIContextEngine" in source, (
        "SP-AGT-003: context_engine: IAIContextEngine parameter missing from CopilotService.__init__"
    )


def test_handle_turn_calls_context_engine_before_twin_service() -> None:
    """context_engine.enrich() must be primary path; twin_service is elif fallback -- SP-AGT-003."""
    source = Path("src/core/copilot/service.py").read_text(encoding="utf-8")
    engine_pos = source.find("self._context_engine.enrich")
    twin_pos = source.find("self._twin_service.get_profile")
    assert engine_pos != -1, "SP-AGT-003: self._context_engine.enrich() not found in service.py"
    assert twin_pos != -1, (
        "SP-AGT-003: self._twin_service.get_profile() not found in service.py (fallback missing)"
    )
    assert engine_pos < twin_pos, (
        "SP-AGT-003: context_engine.enrich() must appear BEFORE twin_service.get_profile() in service.py"
    )


def test_dependencies_injects_context_engine() -> None:
    """_build_copilot_service must inject AIContextEngine -- SP-AGT-003."""
    source = Path("src/core/copilot/dependencies.py").read_text(encoding="utf-8")
    assert "AIContextEngine" in source, (
        "SP-AGT-003: AIContextEngine not imported/used in dependencies.py"
    )
    assert "context_engine=" in source, (
        "SP-AGT-003: context_engine= kwarg missing from CopilotService() call in dependencies.py"
    )


def test_context_engine_log_does_not_leak_exception_message() -> None:
    """context_engine.py error log must not format raw exception in message -- SP-AGT-003 security."""
    source = Path("src/core/agents/context_engine.py").read_text(encoding="utf-8")
    lines = source.splitlines()
    in_except = False
    for i, line in enumerate(lines):
        if "except Exception as exc" in line:
            in_except = True
        if in_except and "logger.error" in line:
            block = "\n".join(lines[i : i + 8])
            assert '", exc,' not in block and '", exc\n' not in block, (
                f"SP-AGT-003: raw exc leaked in logger.error at line {i + 1} of context_engine.py"
            )
            in_except = False
