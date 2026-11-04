"""
Unit tests for Co-Pilot Pydantic schemas.

Test taxonomy per CLAUDE.md kwaliteitsloop:
    - Happy paths      (valid construction)
    - Unhappy paths    (validation errors)
    - Edge cases       (boundary values)

Markers:
    @pytest.mark.unit
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.copilot.schemas import CopilotAction, CopilotTurnRequest


@pytest.mark.unit
class TestCopilotAction:
    """Validation rules for the strict LLM JSON contract."""

    def test_copilot_action_confidence_must_be_between_0_and_1(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CopilotAction(
                message="Hello",
                action="navigate",
                confidence=1.5,
                reasoning="Test",
            )
        assert "confidence" in str(exc_info.value)

    def test_copilot_action_message_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CopilotAction(
                message="",
                action="navigate",
                confidence=0.5,
                reasoning="Test",
            )
        assert "message" in str(exc_info.value)

    def test_copilot_action_action_optional(self) -> None:
        action = CopilotAction(
            message="Hello",
            action=None,
            confidence=0.5,
            reasoning="Test",
        )
        assert action.action is None

    def test_copilot_action_params_default_empty_dict(self) -> None:
        action = CopilotAction(
            message="Hello",
            confidence=0.5,
            reasoning="Test",
        )
        assert action.action_params == {}

    def test_copilot_action_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CopilotAction(
                message="Hello",
                confidence=0.5,
                reasoning="Test",
                extra_field="not_allowed",
            )
        assert "extra_field" in str(exc_info.value)


@pytest.mark.unit
class TestCopilotTurnRequest:
    """Request schema validation."""

    def test_copilot_turn_request_stream_defaults_false(self) -> None:
        req = CopilotTurnRequest(message="Hello")
        assert req.stream is False

    def test_copilot_turn_request_language_defaults_nl(self) -> None:
        req = CopilotTurnRequest(message="Hello")
        assert req.language == "nl"
