import json

import pytest

from src.domains.agentic.graph.state import AgentState
from src.domains.agentic.nodes.focus_generator import focus_generator_node


class _NepModel:
    """Het taalmodel van de tenant (`TenantTaalmodel`), met een vast antwoord."""

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self.vragen: list[tuple[str, str | None]] = []

    async def tekst(self, prompt: str, *, systeem: str | None = None, **_rest: object) -> str:
        self.vragen.append((prompt, systeem))
        return json.dumps(
            {"focus_flow": {"graph": {"nodes": [{"id": "1", "type": "trigger"}], "edges": []}}}
        )


@pytest.mark.asyncio
async def test_focus_generator_node_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify focus_generator_node calls the tenant's model and parses JSON output."""
    model = _NepModel(7)
    monkeypatch.setattr(
        "src.domains.agentic.nodes.focus_generator.TenantTaalmodel", lambda tenant_id: model
    )
    initial_state: AgentState = {
        "input": "Create a flow",
        "tenant_id": 7,
        "chat_history": [],
        "intermediate_steps": [],
        "focus_flow": None,
    }

    new_state_update = await focus_generator_node(initial_state)

    assert model.vragen[0][0] == "Create a flow"
    assert "focus_flow" in new_state_update
    assert len(new_state_update["focus_flow"]["graph"]["nodes"]) == 1
    assert new_state_update["focus_flow"]["graph"]["nodes"][0]["id"] == "1"
