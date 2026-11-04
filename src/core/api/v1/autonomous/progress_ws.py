"""
WebSocket endpoint for real-time workflow progress streaming.
Bridges Redis Streams -> WebSocket for client consumption.
Feature 2: Autonomous Agents - Progress API
"""

import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.api.v1.autonomous.dependencies import get_redis_client
from src.core.auth.api_deps import WebSocketAuthenticator

_auth = WebSocketAuthenticator()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workflow-progress"])

# Allowlist: only exactly "workflow:<task_id>:progress" where task_id contains
# no colons or slashes.  This blocks path-traversal and arbitrary key reads.
_STREAM_KEY_RE = re.compile(r"^workflow:[a-zA-Z0-9_-]+:progress$")


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    """Close websocket, suppressing errors on already-closed connections."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        pass


@router.websocket("/ws/workflow-progress/{stream_key:path}")
async def workflow_progress_ws(websocket: WebSocket, stream_key: str) -> None:
    """
    WebSocket endpoint that streams workflow progress from Redis Streams.

    stream_key format: workflow:<task_id>:progress

    Security:
    - stream_key is validated against a strict regex before any Redis access.
    - A Redis ownership key (workflow:<task_id>:tenant) is checked to ensure
      the authenticated user's tenant matches the stream owner.  Cross-tenant
      access is rejected with close code 4003.
    """
    user = await _auth.authenticate(websocket)
    if not user:
        return

    # 1. Validate stream_key format -- reject anything that doesn't match.
    if not _STREAM_KEY_RE.fullmatch(stream_key):
        logger.warning(
            "Invalid stream_key format rejected: %s (user tenant %s)",
            stream_key,
            user.tenant_id,
        )
        await _close(websocket, 4003, "Invalid stream key format")
        return

    # 2. Extract task_id and look up the tenant ownership key in Redis.
    #    Format: workflow:<task_id>:progress  -> task_id is the middle segment.
    task_id = stream_key[len("workflow:") : -len(":progress")]
    owner_redis_key = f"workflow:{task_id}:tenant"

    redis = await get_redis_client()

    raw_owner = await redis.get(owner_redis_key)
    if raw_owner is not None:
        owner_tenant = int(raw_owner)
        if owner_tenant != user.tenant_id:
            logger.warning(
                "Cross-tenant stream access denied: user tenant=%s, stream tenant=%s, key=%s",
                user.tenant_id,
                owner_tenant,
                stream_key,
            )
            await _close(websocket, 4003, "Access denied: stream belongs to a different tenant")
            return
    else:
        # No ownership record -- stream may be legacy or not yet created.
        # Log a security warning; proceed so existing clients are not broken.
        logger.warning(
            "No ownership record for stream %s (user tenant %s) -- proceeding without tenant check",
            stream_key,
            user.tenant_id,
        )

    logger.info("WebSocket connected for stream: %s (tenant %s)", stream_key, user.tenant_id)

    last_id = "0"  # Start from beginning of stream

    try:
        while True:
            # Read from Redis Stream with blocking (timeout 5s)
            messages = await redis.xread(
                {stream_key: last_id},
                count=10,
                block=5000,
            )

            if messages:
                for _, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        last_id = message_id

                        event = {
                            "id": message_id,
                            "type": message_data.get("type", "unknown"),
                            "data": json.loads(message_data.get("data", "{}")),
                            "timestamp": message_data.get("timestamp"),
                        }

                        await websocket.send_json(event)

                        if event["type"] in ["workflow_completed", "workflow_failed"]:
                            logger.info(
                                "Workflow stream %s ended with %s", stream_key, event["type"]
                            )
                            await _close(websocket, 1000, "")
                            return
            else:
                # No messages -- send heartbeat to keep connection alive.
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for stream: %s", stream_key)
    except Exception as e:
        logger.error("WebSocket error for stream %s: %s: %s", stream_key, type(e).__name__, e)
        try:
            await websocket.send_json({"type": "error", "message": "Internal error"})
        except Exception:
            pass
    finally:
        await _close(websocket, 1000, "")
