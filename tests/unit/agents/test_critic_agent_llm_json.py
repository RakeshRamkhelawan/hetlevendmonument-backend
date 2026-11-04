"""SP-AGT-005 Dag 3: _llm_critique() must parse structured JSON output.

TDD -- tests are RED before the fix, GREEN after.

Fix: prompt changed to JSON-only format; parser changed from text-regex to json.loads().
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.critic_agent import CriticAgent
from src.core.shared.interfaces import ExecutionResult


@pytest.fixture(autouse=True)
def reset_critic_agent_singleton():  # type: ignore[return]
    CriticAgent._instances.clear()
    yield
    CriticAgent._instances.clear()


def _make_result(output: str = "agent output", success: bool = True) -> ExecutionResult:
    return ExecutionResult(
        task_id="task-dag3",
        success=success,
        output=output,
        execution_time=0.1,
    )


def _make_llm_response(content: str) -> dict[str, Any]:
    return {"success": True, "content": content}


@pytest.mark.asyncio
async def test_llm_critique_parses_valid_json() -> None:
    """_llm_critique() must extract score/issues/suggestions from valid JSON response."""
    agent = CriticAgent(tenant_id=1)
    result = _make_result()

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=_make_llm_response(
            '{"score": 0.8, "issues": ["short output"], "suggestions": ["add detail"]}'
        )
    )

    with patch.object(agent, "_get_llm_client", return_value=mock_llm):
        score, issues, suggestions = await agent._llm_critique("test_agent", result)

    assert score == pytest.approx(0.8)
    assert issues == ["short output"]
    assert suggestions == ["add detail"]


@pytest.mark.asyncio
async def test_llm_critique_falls_back_on_bad_json(caplog: pytest.LogCaptureFixture) -> None:
    """_llm_critique() must fall back to defaults and log a warning on unparseable response."""
    agent = CriticAgent(tenant_id=1)
    result = _make_result()

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=_make_llm_response("SCORE: 0.8\nISSUES:\n- short output")
    )

    with patch.object(agent, "_get_llm_client", return_value=mock_llm):
        with caplog.at_level(logging.WARNING, logger="src.core.agents.critic_agent"):
            score, issues, suggestions = await agent._llm_critique("test_agent", result)

    assert score == pytest.approx(0.5)
    assert len(issues) == 1
    assert "parse error" in issues[0].lower() or "manually" in issues[0].lower()
    assert any("parse" in record.getMessage().lower() for record in caplog.records)
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(r.exc_info is not None for r in warning_records), (
        "Warning must include exc_info (stacktrace) -- exc_info=True missing in _llm_critique"
    )


@pytest.mark.asyncio
async def test_llm_critique_tolerates_missing_keys() -> None:
    """_llm_critique() must default issues/suggestions to [] when keys absent from JSON."""
    agent = CriticAgent(tenant_id=1)
    result = _make_result()

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value=_make_llm_response('{"score": 0.7}'))

    with patch.object(agent, "_get_llm_client", return_value=mock_llm):
        score, issues, suggestions = await agent._llm_critique("test_agent", result)

    assert score == pytest.approx(0.7)
    assert issues == []
    assert suggestions == []


@pytest.mark.asyncio
async def test_llm_critique_clamps_out_of_range_score() -> None:
    """Score outside [0.0, 1.0] from LLM must be clamped -- prevents corrupt health metrics."""
    agent = CriticAgent(tenant_id=1)
    result = _make_result()

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=_make_llm_response('{"score": 999, "issues": [], "suggestions": []}')
    )

    with patch.object(agent, "_get_llm_client", return_value=mock_llm):
        score, _, _ = await agent._llm_critique("test_agent", result)

    assert 0.0 <= score <= 1.0, f"Score {score} is outside [0.0, 1.0] -- clamping missing"
