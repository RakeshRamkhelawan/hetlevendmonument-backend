# tests/core/api/v1/focus_builder/test_ws_chat.py
"""
Unit tests for WS chat message dispatch — Task 8.

Strategy: mock the WebSocket and FocusBuilderChatAgent directly, then call
the router's dispatch logic by invoking the handler coroutine.  This avoids
the need for a full ASGI/WS test fixture while still exercising the actual
routing code paths.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_websocket(messages: list) -> MagicMock:
    """Return a mock WebSocket that yields *messages* then raises WebSocketDisconnect."""
    from fastapi import WebSocketDisconnect

    ws = MagicMock()
    # SEC-AGT-004: de handler leest het token uitsluitend uit deze cookie; het
    # ?token=-pad is verwijderd (2026-07-31).
    ws.cookies = {"access_token": "dummy-token"}

    # receive_json returns each message in turn, then raises disconnect
    side_effects = list(messages) + [WebSocketDisconnect()]
    ws.receive_json = AsyncMock(side_effect=side_effects)
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _make_agent() -> MagicMock:
    """Return a mock FocusBuilderChatAgent with relevant async methods."""
    agent = MagicMock()
    agent.start_session = AsyncMock()
    agent.handle_message = AsyncMock()
    agent.handle_refine = AsyncMock()
    agent.handle_explain = AsyncMock()
    agent.accept_proposal = MagicMock(return_value=[])
    agent.reject_proposal = MagicMock()
    return agent


async def _run_handler_with_agent(ws: MagicMock, agent: MagicMock) -> None:
    """
    Import and call the focus_builder_ws_chat handler with a pre-built
    agent mock, bypassing auth by patching validate_ws_token and
    FocusBuilderChatAgent constructor.
    """
    # NOTE: importeren uit ws_chat_router, niet uit de ADR-033-composite router.py --
    # die exporteert de handler niet en heeft dat ook nooit gedaan, waardoor deze 5
    # tests met een ImportError rood stonden. Onopgemerkt gebleven omdat tests/core/
    # buiten zowel `pytest tests/unit/` als `pytest tests/integration/` valt
    # (gevonden tijdens OP-11, 2026-07-31).
    from src.core.api.v1.focus_builder.ws_chat_router import focus_builder_ws_chat

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.tenant_id = 1

    with (
        patch(
            "src.core.api.v1.focus_builder.ws_chat_router.validate_ws_token",
            new_callable=AsyncMock,
            return_value=mock_user,
        ),
        patch(
            "src.core.api.v1.focus_builder.ws_chat_router.FocusBuilderChatAgent",
            return_value=agent,
        ),
    ):
        await focus_builder_ws_chat(
            websocket=ws,
            conversation_id=None,
            db=MagicMock(),
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refine_dispatches_to_handle_refine():
    """A 'refine' WS message must call agent.handle_refine with correct args."""
    nodes = [{"id": "n1", "type": "trigger"}, {"id": "n2", "type": "action"}]
    msg = {
        "type": "refine",
        "content": "add an email step",
        "current_nodes": nodes,
    }
    ws = _make_websocket([msg])
    agent = _make_agent()

    await _run_handler_with_agent(ws, agent)

    agent.handle_refine.assert_awaited_once_with(
        content="add an email step",
        current_nodes=nodes,
    )


@pytest.mark.asyncio
async def test_refine_non_list_current_nodes_returns_error():
    """A 'refine' message with current_nodes as non-list must return an error JSON."""
    msg = {
        "type": "refine",
        "content": "tweak it",
        "current_nodes": "not-a-list",
    }
    ws = _make_websocket([msg])
    agent = _make_agent()

    await _run_handler_with_agent(ws, agent)

    # handle_refine must NOT have been called
    agent.handle_refine.assert_not_awaited()

    # send_json must have been called with the error payload
    error_calls = [
        call
        for call in ws.send_json.await_args_list
        if call.args
        and isinstance(call.args[0], dict)
        and call.args[0].get("type") == "error"
        and call.args[0].get("message") == "current_nodes must be a list"
    ]
    assert len(error_calls) == 1, (
        f"Expected exactly one error send_json call, got: {ws.send_json.await_args_list}"
    )


@pytest.mark.asyncio
async def test_refine_payload_too_large_returns_error():
    """A 'refine' message exceeding 200 KB must return payload_too_large error."""
    # Build a message whose str-encoded size exceeds 200_000 bytes
    big_content = "x" * 201_000
    msg = {
        "type": "refine",
        "content": big_content,
        "current_nodes": [],
    }
    ws = _make_websocket([msg])
    agent = _make_agent()

    await _run_handler_with_agent(ws, agent)

    agent.handle_refine.assert_not_awaited()

    error_calls = [
        call
        for call in ws.send_json.await_args_list
        if call.args
        and isinstance(call.args[0], dict)
        and call.args[0].get("type") == "error"
        and call.args[0].get("message") == "payload_too_large"
    ]
    assert len(error_calls) == 1, (
        f"Expected payload_too_large error, got: {ws.send_json.await_args_list}"
    )


@pytest.mark.asyncio
async def test_explain_dispatches_to_handle_explain():
    """An 'explain' WS message must call agent.handle_explain with correct args."""
    msg = {
        "type": "explain",
        "node_id": "node-42",
        "node_title": "Send Email",
        "node_type": "action",
    }
    ws = _make_websocket([msg])
    agent = _make_agent()

    await _run_handler_with_agent(ws, agent)

    agent.handle_explain.assert_awaited_once_with(
        node_id="node-42",
        node_title="Send Email",
        node_type="action",
    )


@pytest.mark.asyncio
async def test_explain_missing_node_id_is_silently_ignored():
    """An 'explain' message with no node_id must be silently dropped (no error sent)."""
    msg = {
        "type": "explain",
        "node_title": "Send Email",
        "node_type": "action",
        # node_id intentionally omitted
    }
    ws = _make_websocket([msg])
    agent = _make_agent()

    await _run_handler_with_agent(ws, agent)

    agent.handle_explain.assert_not_awaited()
    # No error message should be sent
    error_calls = [
        call
        for call in ws.send_json.await_args_list
        if call.args and isinstance(call.args[0], dict) and call.args[0].get("type") == "error"
    ]
    assert len(error_calls) == 0, (
        f"Expected no error sends for missing node_id, got: {ws.send_json.await_args_list}"
    )
