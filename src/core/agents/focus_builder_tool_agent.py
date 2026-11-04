"""
FocusBuilderToolAgent -- Tool-calling scaffold for Focus Builder.

Activated via FOCUS_BUILDER_TOOL_AGENT=true (settings.focus_builder_tool_agent).
Identical public interface to FocusBuilderChatAgent.

Status: SCAFFOLD -- tool implementations are stubs. Activate only for internal testing.
"""

from __future__ import annotations

import uuid
from typing import Any
from collections.abc import Callable

from loguru import logger

TOOLS = [
    {
        "name": "get_live_integrations",
        "description": "Haal actieve Activepieces-verbindingen op voor deze tenant.",
        "parameters": {
            "type": "object",
            "properties": {"tenant_id": {"type": "integer"}},
            "required": ["tenant_id"],
        },
    },
    {
        "name": "get_agents_for_department",
        "description": "Geef alle agents terug voor een specifiek department.",
        "parameters": {
            "type": "object",
            "properties": {"department": {"type": "string"}},
            "required": ["department"],
        },
    },
    {
        "name": "suggest_refinement",
        "description": "Genereer verfijningsopties op basis van de huidige workflow.",
        "parameters": {
            "type": "object",
            "properties": {
                "current_nodes": {"type": "array"},
                "user_request": {"type": "string"},
            },
            "required": ["current_nodes", "user_request"],
        },
    },
    {
        "name": "explain_node",
        "description": "Geef uitgebreide uitleg van wat een specifieke agent doet.",
        "parameters": {
            "type": "object",
            "properties": {"agent_id": {"type": "string"}},
            "required": ["agent_id"],
        },
    },
]


class FocusBuilderToolAgent:
    """
    Tool-calling agent scaffold. Falls back to FocusBuilderChatAgent on tool error.
    Same interface as FocusBuilderChatAgent -- router uses both interchangeably.
    """

    def __init__(
        self,
        user_id: int,
        tenant_id: int,
        user_id_str: str,
        db: Any,  # TODO(TYPE): replace Any with concrete type
        send_json: Callable[[dict[str, Any]], Any],  # TODO(TYPE): replace Any with concrete type
        restore_conversation_id: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.user_id_str = user_id_str
        self.db = db
        self.send_json = send_json
        self._is_restore = restore_conversation_id is not None
        self.conversation_id = restore_conversation_id or str(uuid.uuid4())
        self._pending_proposals: dict[
            str, list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self._proposal_intakes: dict[
            str, dict[str, Any]
        ] = {}  # TODO(TYPE): replace Any with concrete type

        # Fallback agent for error recovery
        from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent

        self._fallback = FocusBuilderChatAgent(
            user_id=user_id,
            tenant_id=tenant_id,
            user_id_str=user_id_str,
            db=db,
            send_json=send_json,
            restore_conversation_id=restore_conversation_id,
        )

    async def start_session(self) -> None:
        logger.info("tool_agent_session_start", user_id=self.user_id)
        await self._fallback.start_session()

    async def handle_message(self, content: str) -> None:
        logger.info("tool_agent_handle_message", user_id=self.user_id)
        try:
            await self._dispatch_tools(content)
        except Exception as exc:
            logger.warning("tool_agent_fallback", error=str(exc))
            await self._fallback.handle_message(content)

    async def accept_proposal(
        self, proposal_id: str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        return await self._fallback.accept_proposal(proposal_id)

    def reject_proposal(self, proposal_id: str) -> None:
        self._fallback.reject_proposal(proposal_id)

    async def handle_node_updated(
        self,
        node_id: str,
        old_agent_id: str,
        new_agent_id: str,
        workflow_id: int | None = None,
    ) -> None:
        await self._fallback.handle_node_updated(node_id, old_agent_id, new_agent_id, workflow_id)

    async def handle_template_action(self, action: str, template_id: str) -> None:
        await self._fallback.handle_template_action(action, template_id)

    async def handle_refine(
        self,
        content: str,
        current_nodes: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        await self._fallback.handle_refine(content, current_nodes)

    async def handle_explain(self, node_id: str, node_title: str, node_type: str) -> None:
        await self._fallback.handle_explain(node_id, node_title, node_type)

    async def _dispatch_tools(self, content: str) -> None:
        """Scaffold: dispatch tool calls based on content.

        SP-WE-22 / NEW-WIRE-006: tool-calling loop is not yet implemented.
        Logs a WARNING and delegates to the FocusBuilderChatAgent fallback
        instead of raising NotImplementedError, so callers (handle_message,
        WebSocket dispatch) never see an unhandled exception.
        """
        logger.warning(
            "focus_builder_tool_agent_not_implemented_fallback",
            tenant_id=self.tenant_id,
            tool_count=len(TOOLS),
            content_preview=content[:50],
        )
        await self._fallback.handle_message(content)

    def _log_tool_call(
        self,
        name: str,
        args: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        logger.info("tool_agent_call", tool=name, args=args, tenant_id=self.tenant_id)
