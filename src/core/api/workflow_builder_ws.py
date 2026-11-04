"""
Workflow Builder WebSocket - Real-time streaming endpoint.

Provides live keyword extraction and node suggestions via WebSocket.
"""

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.core.api.workflow_builder_endpoints import (
    extract_keywords,
    get_tool_by_keyword,
)
from src.core.auth.api_deps import WebSocketAuthenticator

_auth = WebSocketAuthenticator()

router = APIRouter(tags=["Workflow Builder WebSocket"])
logger = logging.getLogger("workflow_builder_ws")

# =============================================================================
# CONNECTION MANAGER
# =============================================================================


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected. Total: {len(self.active_connections)}")

    def disconnect(self, client_id: str) -> None:
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected. Total: {len(self.active_connections)}")

    async def send_message(self, client_id: str, message: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message to {client_id}: {e}")
                self.disconnect(client_id)


manager = ConnectionManager()

# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================


@router.websocket("/api/v1/builder/stream")
async def workflow_builder_stream(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time workflow building.

    Incoming messages:
    - { type: "keywords", text: "..." }  -> Extract keywords in real-time
    - { type: "suggest", prompt: "...", currentNodes: [...] }  -> Stream suggestions

    Outgoing messages:
    - { type: "keyword", data: { keywords: [...] } }
    - { type: "suggestion", data: { suggestion: {...} } }
    - { type: "complete", data: { message: "..." } }
    - { type: "error", data: { error: "..." } }
    """
    user = await _auth.authenticate(websocket)
    if not user:
        return

    client_id = str(uuid.uuid4())

    await manager.connect(websocket, client_id)

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "keywords":
                # Real-time keyword extraction
                text = data.get("text", "")
                keywords = extract_keywords(text)
                await manager.send_message(
                    client_id, {"type": "keyword", "data": {"keywords": keywords}}
                )

            elif msg_type == "suggest":
                # Stream node suggestions
                prompt = data.get("prompt", "")
                current_nodes = data.get("currentNodes", [])

                # Extract keywords
                keywords = extract_keywords(prompt)

                # Send keywords first
                await manager.send_message(
                    client_id, {"type": "keyword", "data": {"keywords": keywords}}
                )

                # Stream suggestions one by one with delay for effect
                suggestions_sent = 0
                position_y = 100

                for i, keyword in enumerate(keywords):
                    tool = get_tool_by_keyword(keyword)
                    if tool and tool.id not in current_nodes:
                        # Small delay between suggestions for streaming effect
                        await asyncio.sleep(0.3)

                        suggestion = {
                            "id": f"ghost_{keyword}_{i}",
                            "title": tool.name,
                            "description": tool.description,
                            "icon": tool.icon,
                            "phase": tool.phase,
                            "confidence": 0.85,
                            "suggestedPosition": {
                                "x": 300 + (i * 250),
                                "y": position_y,
                            },
                            "sourceKeyword": keyword,
                        }

                        await manager.send_message(
                            client_id,
                            {"type": "suggestion", "data": {"suggestion": suggestion}},
                        )
                        suggestions_sent += 1

                # If no suggestions, send a default one
                if suggestions_sent == 0 and prompt:
                    await asyncio.sleep(0.3)
                    await manager.send_message(
                        client_id,
                        {
                            "type": "suggestion",
                            "data": {
                                "suggestion": {
                                    "id": "ghost_ai_default",
                                    "title": "AI Generate",
                                    "description": f"Generate content for: {prompt[:50]}...",
                                    "icon": "sparkles",
                                    "phase": "create",
                                    "confidence": 0.7,
                                    "suggestedPosition": {"x": 300, "y": 100},
                                    "sourceKeyword": "ai",
                                }
                            },
                        },
                    )
                    suggestions_sent = 1

                # Send completion
                await manager.send_message(
                    client_id,
                    {
                        "type": "complete",
                        "data": {
                            "message": f"Found {suggestions_sent} suggestions for your workflow."
                        },
                    },
                )

            else:
                await manager.send_message(
                    client_id,
                    {
                        "type": "error",
                        "data": {"error": f"Unknown message type: {msg_type}"},
                    },
                )

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        manager.disconnect(client_id)
