"""Action handlers for detected intents.

Each handler processes a specific intent type and performs
the appropriate action (unsubscribe, approve, create ticket, etc.)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

from src.core.notifications.inbound.intent_detector import DetectedIntent
from src.core.notifications.inbound.models import (
    ContactOptOut,
    EmailBounce,
    InboundMessage,
    IntentType,
)


class ActionHandler(ABC):
    """Base class for action handlers."""

    @abstractmethod
    async def can_handle(self, intent: DetectedIntent) -> bool:
        """Check if this handler can process the intent."""
        pass

    @abstractmethod
    async def handle(
        self, message: InboundMessage, intent: DetectedIntent, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process the intent and return result."""
        pass


class UnsubscribeHandler(ActionHandler):
    """Handle STOP/unsubscribe requests.

    Processes opt-out requests across all channels.
    Ensures GDPR compliance by logging opt-outs.
    """

    async def can_handle(self, intent: DetectedIntent) -> bool:
        """Check if intent is unsubscribe."""
        return intent.type == IntentType.UNSUBSCRIBE

    async def handle(
        self, message: InboundMessage, intent: DetectedIntent, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process unsubscribe request.

        Args:
            message: The inbound message
            intent: The detected intent
            tenant_id: Optional tenant ID for multi-tenant setups

        Returns: Dict[str, Any] with result and optional reply message  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # Create opt-out record
            opt_out = ContactOptOut(
                tenant_id=tenant_id,
                contact=message.from_address,
                contact_type="email" if message.channel == "email" else "phone",
                source="user_request",
                channel=message.channel,
                opted_out_at=datetime.now(timezone.utc),
                inbound_message_id=message.id,
            )

            # TODO: Save to database
            logger.info(
                f"Processed unsubscribe for {message.from_address} " f"on channel {message.channel}"
            )

            # Return appropriate confirmation message
            if message.channel == "sms":
                reply = "Je bent uitgeschreven. Je ontvangt geen SMS meer."
            elif message.channel == "email":
                reply = "You have been unsubscribed. You will no longer receive " "emails from us."
            else:
                reply = "You have been unsubscribed."

            return {
                "success": True,
                "action": "unsubscribed",
                "reply_message": reply,
                "opt_out_id": str(opt_out.id) if opt_out.id else None,
            }

        except Exception as e:
            logger.error(f"Failed to process unsubscribe: {e}")
            return {
                "success": False,
                "action": "unsubscribe_failed",
                "error": str(e),
            }


class ApprovalHandler(ActionHandler):
    """Handle approval/rejection via email/SMS.

    Processes approval requests that come in via reply
    to approval notification emails or SMS.
    """

    async def can_handle(self, intent: DetectedIntent) -> bool:
        """Check if intent is approval or rejection."""
        return intent.type in (IntentType.APPROVE, IntentType.REJECT)

    async def handle(
        self, message: InboundMessage, intent: DetectedIntent, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process approval/rejection.

        Args:
            message: The inbound message
            intent: The detected intent (approve or reject)
            tenant_id: Optional tenant ID

        Returns: Dict[str, Any] with result and optional reply message  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # Extract approval code if present
            approval_code = intent.entities.get("approval_code")

            # TODO: Find pending approval request
            # This would query the database for:
            # - By approval code (if provided)
            # - By sender email + thread_id (if reply to approval email)
            # - Most recent pending approval for sender

            approval_request = None  # Placeholder

            if not approval_request:
                logger.warning(f"No pending approval found for {message.from_address}")
                return {
                    "success": False,
                    "action": "approval_not_found",
                    "reply_message": (
                        "No pending approval request found for your account. "
                        "Please check your email for the correct approval link."
                    ),
                }

            # Process the action
            if intent.type == IntentType.APPROVE:
                # TODO: Update approval request status
                logger.info(f"Approved request via {message.channel}")

                reply = f"Approved: {approval_request.title}"
                return {
                    "success": True,
                    "action": "approved",
                    "approval_id": str(approval_request.id),
                    "reply_message": reply,
                }
            else:
                # TODO: Update approval request status with rejection reason
                logger.info(f"Rejected request via {message.channel}")

                reply = f"Rejected: {approval_request.title}"
                return {
                    "success": True,
                    "action": "rejected",
                    "approval_id": str(approval_request.id),
                    "reply_message": reply,
                }

        except Exception as e:
            logger.error(f"Failed to process approval: {e}")
            return {
                "success": False,
                "action": "approval_failed",
                "error": str(e),
            }


class TicketHandler(ActionHandler):
    """Create ticket from inbound message.

    When intent cannot be determined or requires
    human intervention, create a support ticket.
    """

    async def can_handle(self, intent: DetectedIntent) -> bool:
        """This handler can handle any intent as fallback."""
        return True  # Fallback handler

    async def handle(
        self, message: InboundMessage, intent: DetectedIntent, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create support ticket from message.

        Args:
            message: The inbound message
            intent: The detected intent
            tenant_id: Optional tenant ID

        Returns: Dict[str, Any] with result and optional reply message  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # TODO: Create support ticket in database
            # ticket = Ticket(
            #     tenant_id=tenant_id,
            #     subject=message.subject or "Inbound message",
            #     description=message.body_text,
            #     source=message.channel,
            #     customer_email=message.from_address,
            #     status="open",
            #     inbound_message_id=message.id,
            # )

            ticket_id = "TKT-12345"  # Placeholder

            logger.info(
                f"Created ticket {ticket_id} from {message.channel} " f"by {message.from_address}"
            )

            # Return confirmation
            if message.channel == "sms":
                reply = f"Thank you. Ticket {ticket_id} created. We'll respond shortly."
            else:
                reply = (
                    f"Thank you for your message. Support ticket {ticket_id} "
                    f"has been created. Our team will respond within 24 hours."
                )

            return {
                "success": True,
                "action": "ticket_created",
                "ticket_id": ticket_id,
                "reply_message": reply,
            }

        except Exception as e:
            logger.error(f"Failed to create ticket: {e}")
            return {
                "success": False,
                "action": "ticket_creation_failed",
                "error": str(e),
            }


class BounceHandler(ActionHandler):
    """Handle email bounce notifications.

    Processes bounce messages to maintain sender reputation
    and suppress invalid addresses.
    """

    async def can_handle(self, intent: DetectedIntent) -> bool:
        """Check if intent is bounce."""
        return intent.type == IntentType.BOUNCE

    async def handle(
        self, message: InboundMessage, intent: DetectedIntent, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process bounce notification.

        Args:
            message: The bounce notification message
            intent: The detected intent
            tenant_id: Optional tenant ID

        Returns: Dict[str, Any] with result  # TODO(TYPE): replace Any with concrete type
        """
        try:
            bounce_type = intent.entities.get("bounce_type", "soft")

            # Extract bounced address from bounce message
            bounced_address = self._extract_bounced_address(message.body_text)

            if bounced_address:
                # Create bounce record
                bounce = EmailBounce(
                    tenant_id=tenant_id,
                    original_message_id=message.in_reply_to,
                    bounce_type=bounce_type,
                    bounced_address=bounced_address,
                    bounced_at=datetime.now(timezone.utc),
                    raw_bounce_content=message.body_text,
                )

                # For hard bounces, mark address as invalid
                if bounce_type == "hard":
                    bounce.marked_invalid = True
                    bounce.suppressed = True

                    # TODO: Also create opt-out for hard bounces
                    logger.warning(f"Hard bounce for {bounced_address} - marking as invalid")

                # TODO: Save to database
                logger.info(f"Processed {bounce_type} bounce for {bounced_address}")

                return {
                    "success": True,
                    "action": "bounce_processed",
                    "bounce_type": bounce_type,
                    "bounced_address": bounced_address,
                }
            else:
                logger.warning("Could not extract bounced address from bounce message")
                return {
                    "success": False,
                    "action": "bounce_parse_failed",
                    "error": "Could not extract bounced address",
                }

        except Exception as e:
            logger.error(f"Failed to process bounce: {e}")
            return {
                "success": False,
                "action": "bounce_processing_failed",
                "error": str(e),
            }

    def _extract_bounced_address(self, body: str | None) -> str | None:
        """Extract the bounced email address from bounce message."""
        if not body:
            return None

        # Common patterns in bounce messages
        patterns = [
            r"Original-Recipient:.*?rfc822;\s*([^\s]+)",
            r"Final-Recipient:.*?rfc822;\s*([^\s]+)",
            r"X-Failed-Recipients:\s*([^\s]+)",
            r"[<\s]([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[>\s]",
        ]

        import re

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1).strip("<>")

        return None


class ActionRouter:
    """Routes detected intents to appropriate handlers.

    Maintains a registry of handlers and routes each intent
    to the first handler that can process it.
    """

    def __init__(self) -> None:
        """Initialize with default handlers."""
        self.handlers: list[ActionHandler] = [
            UnsubscribeHandler(),
            ApprovalHandler(),
            BounceHandler(),
            TicketHandler(),  # Fallback - must be last
        ]

    def register_handler(self, handler: ActionHandler, priority: int = 0) -> None:
        """Register a custom handler.

        Args:
            handler: The handler to register
            priority: Higher priority = earlier in chain (0 = end)
        """
        if priority > 0:
            self.handlers.insert(0, handler)
        else:
            self.handlers.append(handler)

    async def route_and_handle(
        self, message: InboundMessage, intent: DetectedIntent, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Route intent to appropriate handler and execute.

        Args:
            message: The inbound message
            intent: The detected intent
            tenant_id: Optional tenant ID

        Returns:
            Handler result dict
        """
        for handler in self.handlers:
            if await handler.can_handle(intent):
                result = await handler.handle(message, intent, tenant_id)
                result["handler"] = handler.__class__.__name__
                return result

        # Should never reach here (TicketHandler handles everything)
        return {
            "success": False,
            "action": "no_handler_found",
            "error": "No handler found for intent",
        }
