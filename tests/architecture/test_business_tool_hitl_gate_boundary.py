"""Architecture guard: destructive business tools stay behind the HITL gate.

`delete_task` (HIGH risk) is only HITL-gated because it is dispatched through
`ToolBrokerService.execute_tool`, which applies the ADR-015 HIGH-risk gate before
delegating to `BusinessToolRegistry.execute_business_tool`. Calling
`execute_business_tool` directly from anywhere else would perform the destructive
action without the gate.

This test locks that invariant: the registry dispatch may only be invoked by
ToolBrokerService. It is GREEN today and turns RED the moment a bypassing caller
is introduced.

Context: AGENTIC-COPILOT-TAAKBEHEER Dag 4 -- independent-review observation
(HITL enforcement lives only in ToolBrokerService, previously untested).
"""

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"

# Only ToolBrokerService may call the registry dispatch (it enforces the gate).
# The registry module itself is exempt (it defines the method).
_ALLOWED_CALLERS = {"core/tool_broker/service.py"}
_DEFINITION_MODULE = "core/tool_broker/business_registry.py"
_CALL_PATTERN = re.compile(r"\.execute_business_tool\s*\(")


def test_execute_business_tool_only_reachable_via_tool_broker_service() -> None:
    """Direct callers of execute_business_tool would bypass the ADR-015 HITL gate."""
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if rel == _DEFINITION_MODULE or rel in _ALLOWED_CALLERS:
            continue
        if _CALL_PATTERN.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)

    assert not offenders, (
        "BusinessToolRegistry.execute_business_tool must only be invoked by "
        "ToolBrokerService, which applies the ADR-015 HIGH-risk HITL gate. "
        f"These modules call it directly and bypass the gate: {sorted(offenders)}"
    )
