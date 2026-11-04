"""
WebSocket Pusher for cross-node notification delivery via Redis Pub/Sub.

Each node subscribes to ws:user:{user_id} channels and forwards messages
to local WebSocket connections. This file only handles publishing; the
subscriber side lives in ConnectionManager._redis_listener() (SP-WE-02, implemented).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class WSPusher:
    """Publish notifications to a Redis Pub/Sub channel for cross-node WS delivery."""

    CHANNEL_TEMPLATE = "ws:user:{user_id}"

    def __init__(self, redis: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._redis = redis

    async def push(
        self,
        user_id: int,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Publish payload to the per-user Redis channel.

        Callers should wrap this in best_effort() if the push is non-critical.
        Exceptions propagate to the caller on Redis failure.
        """
        channel = self.CHANNEL_TEMPLATE.format(user_id=user_id)
        await self._redis.publish(channel, json.dumps(payload))
        logger.info(
            "ws_push published",
            extra={
                "user_id": user_id,
                "channel": channel,
                "payload_type": payload.get("type"),
            },
        )
