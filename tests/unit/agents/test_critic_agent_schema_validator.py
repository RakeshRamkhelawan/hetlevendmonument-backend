"""TDD tests for OutputSchemaValidator -- SP-AGT-006 Dag 1."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agents.critic_agent import OutputSchemaValidator, CriticAgent, HeuristicScorer


# ---------------------------------------------------------------------------
# Test 1.1
# ---------------------------------------------------------------------------


def test_valid_string_output_passes():
    validator = OutputSchemaValidator(required_type=str)
    result = validator.validate("Dit is een geldige output.")
    assert result.passed is True
    assert result.issues == []


# ---------------------------------------------------------------------------
# Test 1.2
# ---------------------------------------------------------------------------


def test_empty_string_fails_with_score_zero():
    validator = OutputSchemaValidator(required_type=str)
    result = validator.validate("")
    assert result.passed is False
    assert result.score == 0.0
    assert len(result.issues) >= 1


# ---------------------------------------------------------------------------
# Test 1.3
# ---------------------------------------------------------------------------


def test_missing_required_field_fails():
    validator = OutputSchemaValidator(required_fields=["score", "reasoning"])
    result = validator.validate({"score": 0.8})
    assert result.passed is False
    assert any("reasoning" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Test 1.4
# ---------------------------------------------------------------------------


def test_wrong_type_fails_with_score_zero():
    validator = OutputSchemaValidator(required_type=str)
    result = validator.validate({"key": "val"})
    assert result.passed is False
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# Test 1.5
# ---------------------------------------------------------------------------


def test_max_chars_exceeded_fails():
    validator = OutputSchemaValidator(max_chars=50)
    result = validator.validate("x" * 100)
    assert result.passed is False
    assert any("max_chars" in i or "exceed" in i.lower() for i in result.issues)


# ---------------------------------------------------------------------------
# Test 1.6
# ---------------------------------------------------------------------------


def test_none_output_fails_with_score_zero():
    validator = OutputSchemaValidator()
    result = validator.validate(None)
    assert result.passed is False
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# Test 1.7
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_task_skips_llm_on_schema_fail():
    # Reset singleton so we get a fresh instance
    CriticAgent._instances.pop(1, None)
    agent = CriticAgent(tenant_id=1)

    result_mock = MagicMock()
    result_mock.output = ""

    with (
        patch.object(agent, "_llm_critique", new_callable=AsyncMock) as mock_llm,
        patch.object(agent._store, "store", new_callable=AsyncMock),
    ):
        critique = await agent.critique_task(
            agent_name="TestAgent",
            task_id="t1",
            result=result_mock,
            use_llm=True,
        )

    mock_llm.assert_not_called()
    assert critique.score == 0.0


# ---------------------------------------------------------------------------
# Test 1.8
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_task_proceeds_to_heuristic_on_schema_pass():
    # Use tenant_id=2 to get a fresh instance
    CriticAgent._instances.pop(2, None)
    agent = CriticAgent(tenant_id=2)

    result_mock = MagicMock()
    result_mock.output = "Valid output met genoeg tekst hier"

    with (
        patch.object(HeuristicScorer, "score", return_value=(0.9, [], [])) as mock_heuristic,
        patch.object(agent._store, "store", new_callable=AsyncMock),
    ):
        critique = await agent.critique_task(
            agent_name="TestAgent",
            task_id="t2",
            result=result_mock,
            use_llm=False,
        )

    mock_heuristic.assert_called_once()
    assert critique.score > 0.0
