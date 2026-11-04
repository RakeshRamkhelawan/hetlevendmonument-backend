"""
Tests for SP-WE-22: focus_builder_tool_agent NotImplementedError Graceful Fallback.

Source: NEW-WIRE-006
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_agent():
    """Build a FocusBuilderToolAgent with mocked dependencies."""
    from src.core.agents.focus_builder_tool_agent import FocusBuilderToolAgent

    mock_db = MagicMock()
    mock_send_json = AsyncMock()

    with patch("src.core.agents.focus_builder_chat_agent.FocusBuilderChatAgent") as MockFallback:
        mock_fallback_instance = MagicMock()
        mock_fallback_instance.start_session = AsyncMock()
        mock_fallback_instance.handle_message = AsyncMock()
        MockFallback.return_value = mock_fallback_instance

        agent = FocusBuilderToolAgent(
            user_id=1,
            tenant_id=42,
            user_id_str="1",
            db=mock_db,
            send_json=mock_send_json,
        )
        agent._fallback = mock_fallback_instance
        return agent


@pytest.mark.unit
class TestFocusBuilderToolAgentDispatch:
    """Tests for _dispatch_tools graceful fallback -- SP-WE-22 / NEW-WIRE-006."""

    @pytest.mark.asyncio
    async def test_dispatch_tools_does_not_raise(self):
        """_dispatch_tools() must NEVER bubble an exception to the caller."""
        agent = _make_agent()
        await agent._dispatch_tools("maak een workflow voor HR onboarding")

    @pytest.mark.asyncio
    async def test_dispatch_tools_logs_warning_not_implemented(self):
        """_dispatch_tools() emits a WARNING with tenant_id when scaffold active."""
        from src.core.agents import focus_builder_tool_agent as mod

        agent = _make_agent()

        captured: list[str] = []

        def fake_warning(msg, *_args, **_kwargs):
            captured.append(str(msg))

        with patch.object(mod.logger, "warning", side_effect=fake_warning):
            await agent._dispatch_tools("test prompt")

        assert any(
            ("not_implemented" in m.lower()) or ("fallback" in m.lower()) for m in captured
        ), f"Expected a WARNING about fallback, got: {captured}"

    @pytest.mark.asyncio
    async def test_dispatch_tools_delegates_to_fallback(self):
        """_dispatch_tools() must invoke fallback when implementation missing."""
        agent = _make_agent()
        content = "genereer een sales workflow"
        await agent._dispatch_tools(content)
        cast(AsyncMock, agent._fallback.handle_message).assert_awaited_once_with(content)

    @pytest.mark.asyncio
    async def test_handle_message_does_not_raise_when_dispatch_unimplemented(self):
        """handle_message() must never propagate an exception to the API layer."""
        agent = _make_agent()
        await agent.handle_message("test content")
        cast(AsyncMock, agent._fallback.handle_message).assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_tools_no_not_implemented_error_raised(self):
        """Regression: NotImplementedError must NOT bubble anymore."""
        agent = _make_agent()
        try:
            await agent._dispatch_tools("een willekeurige prompt")
        except NotImplementedError as exc:
            pytest.fail(f"_dispatch_tools() still raises NotImplementedError: {exc}")
