"""SP-WE-23: FocusBuilderToolAgent NotImplementedError regression guard."""

from pathlib import Path


def test_focus_builder_tool_agent_no_not_implemented_error() -> None:
    """SP-WE-23: raise NotImplementedError mag niet in focus_builder_tool_agent.py staan."""
    source = Path("src/core/agents/focus_builder_tool_agent.py").read_text(encoding="utf-8")
    assert "raise NotImplementedError" not in source, (
        "SP-WE-23: NotImplementedError gevonden in focus_builder_tool_agent.py -- "
        "dit propageert als HTTP 500 in productie. Vervang door fallback + warning."
    )
