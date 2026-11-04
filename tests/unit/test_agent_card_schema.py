"""Contract tests for canonical Agent Card schema (Phase C2)."""

from src.core.protocol import AgentCard, build_agent_card, validate_agent_card


def test_build_agent_card_applies_defaults() -> None:
    card = build_agent_card(
        agent_id="knowledge_agent",
        name="Knowledge Agent",
        agent_type="specialist",
        description="Indexes and retrieves knowledge",
        capabilities=["search", "index"],
        endpoint="internal://knowledge_agent",
        metadata={"department": "knowledge"},
    )

    assert isinstance(card, AgentCard)
    assert card.agent_id == "knowledge_agent"
    assert card.protocols == ["unified-message-bus-v1"]
    assert card.input_modalities == ["text"]
    assert card.output_modalities == ["text"]


def test_validate_agent_card_rejects_missing_required_fields() -> None:
    invalid = {
        "agent_id": "x",
        "name": "X",
        # missing agent_type
    }

    try:
        validate_agent_card(invalid)
        assert False, "Expected validation to fail for missing required field"
    except Exception:
        assert True
