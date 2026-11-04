import json
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from loguru import logger

from src.core.ratelimit.websocket_limiter import WebSocketLimiter

# Initialize Rate Limiter (5 requests per 60 seconds)
limiter = WebSocketLimiter(rate_limit=5, time_window=60)

from src.core.api.v1.agentic.dependencies import OversightGate
from src.core.auth.api_deps import get_ws_user, AuthenticatedUser
from src.domains.agentic.graph.builder import WorkflowGraphBuilder

router = APIRouter()

# Initialize graph once (or per connection if needed? Builder creates a NEW graph compilation each time)
# Ideally we cache the compiled graph if it's stateless, but LangGraph compilation might be cheap enough.
# For now, we build it per connection to be safe.


@router.websocket("/ws/agent/stream")
async def agent_stream_websocket(
    websocket: WebSocket, user: AuthenticatedUser = Depends(get_ws_user)
) -> None:
    """
    Real-time agent streaming endpoint.
    Streams 'thinking' events and final 'token' events.
    """
    # get_ws_user already accepted the socket; a second accept raises in Starlette.
    logger.info(f"Agent WebSocket connected for user {user.user_id}")

    # 2. Initialize Agent Graph
    try:
        from langgraph.graph import END

        from src.domains.agentic.nodes.focus_generator import focus_generator_node
        from src.domains.agentic.nodes.validator import validate_graph_node

        graph_builder = WorkflowGraphBuilder()
        # Build the graph topology
        graph_builder.graph.add_node("focus_generator", focus_generator_node)
        graph_builder.graph.add_node("validator", validate_graph_node)

        graph_builder.graph.set_entry_point("focus_generator")
        graph_builder.graph.add_edge("focus_generator", "validator")
        graph_builder.graph.add_edge("validator", END)

        app = graph_builder.build()
    except Exception as e:
        logger.error(f"Failed to build agent graph: {e}")
        # Connection is already open, so we can send a close frame
        await websocket.close(code=1011, reason="Internal Error")
        return

    # Governance check before processing any messages
    try:
        from src.core.api.v1.agentic.dependencies import (
            AuditServiceAdapter,
            PolicyEngineAdapter,
        )

        gate = OversightGate(
            policy_engine=PolicyEngineAdapter(), audit_service=AuditServiceAdapter()
        )
        governance_result = await gate.check(
            agent_name="LangGraphStream",
            agent_department="agentic",
            agent_specialisation="stream",
            agent_capabilities=["stream_agent"],
            # SP-GOV-ENTRYPOINT-AUDIT: was "stream", een naam die in geen enkele
            # allowlist stond en dus stil deny-by-default werd geweigerd. De
            # goedgekeurde naam voor dit pad is stream_execution.
            task_action="stream_execution",
            task_params={"user_id": str(user.user_id)},
            tenant_id=user.tenant_id,
            user_id=int(user.user_id) if str(user.user_id).isdigit() else None,
        )
    except Exception as e:
        logger.error(f"Governance check failed: {e}")
        await websocket.close(code=1011, reason="Governance Error")
        return

    if not governance_result.allowed or governance_result.requires_human_approval:
        logger.warning(f"WebSocket blocked by governance: {governance_result.reason}")
        await websocket.close(code=1008, reason=governance_result.reason)
        return

    try:
        while True:
            # 3. Receive User Input
            data = await websocket.receive_text()
            logger.debug(f"Received: {data}")

            # 3.1 Rate Limit Check
            if not limiter.check_limit(str(user.user_id)):
                await websocket.send_json(
                    {"type": "error", "content": "Rate limit exceeded. Please wait."}
                )
                continue

            # 3.2 Input Sanitization
            if len(data) > 2000:
                await websocket.send_json(
                    {"type": "error", "content": "Input too long (max 2000 chars)."}
                )
                continue

            # Basic sanitization (prevent script injection)
            if "<script>" in data.lower():
                await websocket.send_json({"type": "error", "content": "Invalid input detected."})
                continue

            # 4. Stream "Thinking"
            await websocket.send_json({"type": "thinking", "content": "Initializing..."})

            # 5. Invoke Agent with Streaming
            inputs = {"input": data, "chat_history": [], "tenant_id": user.tenant_id}
            final_focus_flow: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            async for event in app.astream_events(inputs, version="v2"):
                kind = event["event"]

                # Stream LLM tokens
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    content = chunk.content if chunk else None
                    if content:
                        await websocket.send_json({"type": "token", "content": content})

                # Capture final output from the validator or graph end
                if kind == "on_chain_end" and event["name"] == "LangGraph":
                    data_output = event["data"].get("output")
                    if data_output:
                        final_focus_flow = (
                            data_output.get("focus_flow", {})
                            if isinstance(data_output, dict)
                            else {}
                        )

                # Log node updates
                event_output = (
                    event["data"].get("output") if isinstance(event["data"], dict) else None
                )
                if (
                    kind == "on_chain_end"
                    and isinstance(event_output, dict)
                    and "focus_flow" in event_output
                ):
                    # Update our running state capture if available
                    final_focus_flow = event_output.get("focus_flow", {})

            # Check for error or send final confirmation
            if "error" in final_focus_flow:
                await websocket.send_json({"type": "error", "content": final_focus_flow["error"]})
            elif final_focus_flow:
                # Send the final validated JSON as a fallback/confirmation
                response_text = json.dumps(final_focus_flow)
                await websocket.send_json({"type": "token", "content": response_text})

    except WebSocketDisconnect:
        logger.info("Agent WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011)
        except Exception as ws_error:
            logger.debug(f"Failed to close agentic websocket: {ws_error}")


@router.websocket("/ws/builder")
async def ws_builder_alias(websocket: WebSocket) -> None:
    """Migration alias -- frontend should use /ws/agent/stream instead."""
    await websocket.accept()
    await websocket.close(code=1001, reason="Moved to /ws/agent/stream")
