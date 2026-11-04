"""ADR-033 criterium 4: focus_builder_chat_agent mag NIET importeren uit src.core.api.*

SP-API-009 Dag 3 -- regressietest voor agent_runtime -> core_api circulaire dep.
"""

import ast
from pathlib import Path

CHAT_AGENT_FILE = "src/core/agents/focus_builder_chat_agent.py"
FORBIDDEN_PREFIX = "src.core.api"


def _get_api_imports(filepath: str) -> list[str]:
    """Geeft alle ImportFrom-nodes terug die src.core.api.* importeren (top-level + function-body)."""
    tree = ast.parse(Path(filepath).read_text(encoding="utf-8"))
    return [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(FORBIDDEN_PREFIX)
    ]


def test_focus_builder_chat_agent_has_no_core_api_imports() -> None:
    """focus_builder_chat_agent.py mag NIET importeren uit src.core.api.*.

    ADR-033 criterium 4: agent_runtime -> core_api circulaire dep moet 0 zijn.
    Huidige schending: regel 361 -- function-body import van _get_internal_agents
    uit src.core.api.v1.focus_builder.agents.
    Fix: verplaats _get_internal_agents naar src.core.als.agents.focus_builder_agents.
    """
    violations = _get_api_imports(CHAT_AGENT_FILE)
    assert violations == [], (
        f"focus_builder_chat_agent.py importeert uit src.core.api.*: {violations}\n"
        "Fix: importeer _get_internal_agents uit src.core.als.agents.focus_builder_agents"
    )
