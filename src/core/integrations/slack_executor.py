"""
Slack Executor for Workflow Integration
========================================

Real Slack integration replacing mock executor.

Features:
- Send messages to channels
- Send direct messages to users
- Add reactions to messages
- Environment-based configuration

Note: Requires 'slack_sdk' package to be installed.
Install with: pip install slack-sdk
"""

import logging
import os
from typing import Any, Optional

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    HAS_SLACK = True
except ImportError:
    HAS_SLACK = False
    WebClient: Any = None  # type: ignore[no-redef]
    SlackApiError: Any = None  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


class SlackExecutor:
    """
    Production Slack executor for workflows.

    Requires environment variable:
        SLACK_BOT_TOKEN: xoxb-your-bot-token

    Usage in workflow node:
        {
            "type": "slack_agent",
            "config": {
                "action": "send_message"|"send_dm"|"reaction",
                "channel": "#general",
                "text": "Message content",
                "user_id": "U123...",
                "emoji": "thumbsup"
            }
        }
    """

    def __init__(self, bot_token: str | None = None) -> None:
        """Initialize Slack client with bot token."""
        if not HAS_SLACK:
            logger.warning(
                "slack_sdk is not installed. Slack functionality will be unavailable. "
                "Install with: pip install slack-sdk"
            )
            self.token = None
            self.client = None
            return

        self.token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        if not self.token:
            logger.warning("SLACK_BOT_TOKEN not set. Slack executor will fail.")
        self.client = WebClient(token=self.token) if self.token else None

    def _get_client(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get Slack client or raise error if not configured."""
        if self.client is None:
            raise RuntimeError("Slack client not configured. SLACK_BOT_TOKEN not set.")
        return self.client

    async def execute(self, node: dict[str, Any], context: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute Slack action based on node configuration.

        Args:
            node: Node configuration with 'config' field
            context: Execution context (not used currently)

        Returns:
            Result dictionary with success status
        """
        if not HAS_SLACK:
            return {
                "success": False,
                "error": ("slack_sdk is not installed. Install with: pip install slack-sdk"),
            }

        if not self.client:
            return {
                "success": False,
                "error": "Slack client not initialized. Check SLACK_BOT_TOKEN.",
            }

        config = node.get("config", {})
        action_type = config.get("action", "send_message")

        try:
            if action_type == "send_message":
                return await self._send_message(config)
            elif action_type == "send_dm":
                return await self._send_dm(config)
            elif action_type == "reaction":
                return await self._add_reaction(config)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action type: {action_type}",
                }

        except Exception as e:
            error_msg = str(e)
            if HAS_SLACK and SlackApiError is not None and isinstance(e, SlackApiError):
                try:
                    slack_response = getattr(e, "response", None)
                    if slack_response is not None:
                        error_msg = slack_response["error"]
                except (KeyError, TypeError):
                    pass
            logger.error(f"Slack API error: {error_msg}")
            return {
                "success": False,
                "error": f"Slack API error: {error_msg}",
                "details": str(e),
            }

    async def _send_message(self, config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Send message to channel."""
        if not self.client:
            return {"success": False, "error": "Slack client not initialized"}

        client = self.client
        channel = config.get("channel")
        text = config.get("text", "")
        blocks = config.get("blocks")

        if not channel:
            return {"success": False, "error": "Missing required field: channel"}

        response = client.chat_postMessage(channel=channel, text=text, blocks=blocks)

        logger.info(f"Sent message to {channel}: {response['ts']}")

        return {
            "success": True,
            "message_ts": response["ts"],
            "channel": response["channel"],
            "text": text,
        }

    async def _send_dm(self, config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Send direct message to user."""
        if not self.client:
            return {"success": False, "error": "Slack client not initialized"}

        client = self.client
        user_id = config.get("user_id")
        text = config.get("text", "")

        if not user_id:
            return {"success": False, "error": "Missing required field: user_id"}

        # Open DM channel
        dm_response = client.conversations_open(users=user_id)
        channel_id = dm_response["channel"]["id"]

        # Send message
        msg_response = client.chat_postMessage(channel=channel_id, text=text)

        logger.info(f"Sent DM to {user_id}: {msg_response['ts']}")

        return {
            "success": True,
            "message_ts": msg_response["ts"],
            "user_id": user_id,
            "text": text,
        }

    async def _add_reaction(self, config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Add reaction emoji to message."""
        if not self.client:
            return {"success": False, "error": "Slack client not initialized"}

        client = self.client
        channel = config.get("channel")
        message_ts = config.get("message_ts")
        emoji = config.get("emoji", "thumbsup")

        if not channel or not message_ts:
            return {
                "success": False,
                "error": "Missing required fields: channel, message_ts",
            }

        client.reactions_add(channel=channel, timestamp=message_ts, name=emoji)

        logger.info(f"Added :{emoji}: to message {message_ts} in {channel}")

        return {
            "success": True,
            "emoji": emoji,
            "channel": channel,
            "message_ts": message_ts,
        }


# Factory function for executor registry
def create_slack_executor() -> "SlackExecutor":
    """Create Slack executor instance."""
    return SlackExecutor()
