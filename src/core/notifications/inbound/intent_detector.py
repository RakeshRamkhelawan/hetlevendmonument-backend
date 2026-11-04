"""Intent detection for inbound messages.

Uses rule-based detection for fast common cases,
with LLM fallback for complex messages.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.notifications.inbound.models import InboundMessage, IntentType


@dataclass
class DetectedIntent:
    """Result of intent detection."""

    type: IntentType
    confidence: float = 0.5
    entities: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    raw_text: str | None = None

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if intent has high confidence."""
        return self.confidence >= threshold


class IntentDetector:
    """Unified intent detection for all inbound channels.

    Uses rules + LLM for complex cases.
    """

    # Command keywords mapped to intents
    COMMAND_KEYWORDS: dict[IntentType, list[str]] = {
        IntentType.UNSUBSCRIBE: [
            "stop",
            "unsubscribe",
            "opzeggen",
            "uitschrijven",
            "afmelden",
            "cancel",
            "end",
        ],
        IntentType.HELP: ["help", "hulp", "support", "assistance", "?"],
        IntentType.APPROVE: [
            "approve",
            "goedkeuren",
            "akkoord",
            "yes",
            "ja",
            "accepted",
            "confirmed",
            "goedgekeurd",
        ],
        IntentType.REJECT: [
            "reject",
            "afkeuren",
            "niet akkoord",
            "no",
            "nee",
            "denied",
            "refused",
            "afgewezen",
        ],
        IntentType.QUERY_STATUS: [
            "status",
            "update",
            "progress",
            "where",
            "waar",
            "hoe staat",
            "wat is de status",
        ],
    }

    def __init__(self, use_llm: bool = False) -> None:
        """Initialize detector.

        Args:
            use_llm: Whether to use LLM for complex detection
        """
        self.use_llm = use_llm

    async def detect_intent(self, message: InboundMessage) -> DetectedIntent:
        """Detect user intent from inbound message.

        Works for email, SMS, WhatsApp.

        Args:
            message: The inbound message to analyze

        Returns:
            DetectedIntent with type, confidence, and entities
        """
        # Step 1: Rule-based detection (fast)
        rule_intent = self._rule_based_detection(message)
        if rule_intent.confidence > 0.9:
            return rule_intent

        # Step 2: LLM-based detection (for complex cases)
        if self.use_llm:
            llm_intent = await self._llm_detection(message)

            # Use LLM if rule confidence is low
            if rule_intent.confidence < 0.7:
                return llm_intent

        return rule_intent

    def _rule_based_detection(self, message: InboundMessage) -> DetectedIntent:
        """Fast rule-based intent detection.

        Analyzes message content for common patterns and commands.
        """
        text = (message.body_text or "").upper().strip()
        subject = (message.subject or "").upper().strip()

        # Check for bounce indicators
        if self._is_bounce(subject, text):
            return DetectedIntent(
                type=IntentType.BOUNCE,
                confidence=0.95,
                entities={"bounce_type": self._detect_bounce_type(text)},
            )

        # Check for out-of-office
        if self._is_out_of_office(subject, text):
            return DetectedIntent(type=IntentType.OUT_OF_OFFICE, confidence=0.95)

        # Check for reply (has in_reply_to or Re: prefix)
        if message.in_reply_to or subject.startswith(("RE:", "AW:", "FW:")):
            # Check if reply contains approval/rejection
            approval_intent = self._detect_approval_in_reply(text)
            if approval_intent:
                return approval_intent

            return DetectedIntent(
                type=IntentType.REPLY,
                confidence=0.8,
                entities={"is_forward": subject.startswith("FW:")},
            )

        # Check for commands (first word)
        first_word = text.split()[0] if text else ""
        for intent_type, keywords in self.COMMAND_KEYWORDS.items():
            if any(
                keyword.upper() == first_word or text.startswith(keyword.upper())
                for keyword in keywords
            ):
                return DetectedIntent(
                    type=intent_type, confidence=0.9, entities={"command": first_word.lower()}
                )

        # Check for approval code pattern (6 chars alphanumeric)
        if re.match(r"^[A-Z0-9]{6}$", text.replace(" ", "")):
            return DetectedIntent(
                type=IntentType.COMMAND,
                confidence=0.85,
                entities={"approval_code": text.replace(" ", "").upper()},
            )

        # Default: unknown intent
        return DetectedIntent(type=IntentType.UNKNOWN, confidence=0.5)

    def _is_bounce(self, subject: str, body: str) -> bool:
        """Detect bounce messages."""
        bounce_indicators = [
            "delivery status notification",
            "undelivered mail",
            "mail delivery failed",
            "message undeliverable",
            "returned mail",
            "bounce",
            "non-delivery report",
        ]
        combined = f"{subject} {body}".lower()
        return any(indicator in combined for indicator in bounce_indicators)

    def _detect_bounce_type(self, text: str) -> str:
        """Detect if bounce is hard or soft."""
        text_lower = text.lower()

        hard_bounce_indicators = [
            "does not exist",
            "invalid address",
            "no such user",
            "user unknown",
            "mailbox unavailable",
            "address rejected",
            "permanent failure",
            "550",
            "551",
            "552",
            "553",
            "554",
        ]

        for indicator in hard_bounce_indicators:
            if indicator in text_lower:
                return "hard"

        return "soft"

    def _is_out_of_office(self, subject: str, body: str) -> bool:
        """Detect out-of-office auto-replies."""
        ooo_indicators = [
            "out of office",
            "out of the office",
            "auto-reply",
            "automatic reply",
            "autoresponder",
            "away from office",
            "abwesenheit",
            "automatische antwort",
            "out of office reply",
        ]
        combined = f"{subject} {body}".lower()
        return any(indicator in combined for indicator in ooo_indicators)

    def _detect_approval_in_reply(self, text: str) -> DetectedIntent | None:
        """Detect approval/rejection in reply messages."""
        text_lower = text.lower()

        # Strong approval indicators
        approval_phrases = [
            "i approve",
            "approved",
            "go ahead",
            "proceed with",
            "goedkeuren",
            "akkoord",
            "goedgekeurd",
            "approved",
            "yes, approve",
            "confirm approval",
        ]

        # Strong rejection indicators
        rejection_phrases = [
            "i reject",
            "rejected",
            "do not proceed",
            "denied",
            "afkeuren",
            "niet akkoord",
            "afgewezen",
            "rejected",
            "no, reject",
            "confirm rejection",
            "disapproved",
        ]

        for phrase in approval_phrases:
            if phrase in text_lower:
                return DetectedIntent(
                    type=IntentType.APPROVE, confidence=0.9, entities={"approval_method": "reply"}
                )

        for phrase in rejection_phrases:
            if phrase in text_lower:
                return DetectedIntent(
                    type=IntentType.REJECT, confidence=0.9, entities={"rejection_method": "reply"}
                )

        return None

    async def _llm_detection(self, message: InboundMessage) -> DetectedIntent:
        """LLM-based detection for complex messages.

        This is a placeholder for LLM integration.
        In production, this would call an LLM service.
        """
        # TODO: Implement LLM-based detection
        # For now, return unknown with medium confidence
        return DetectedIntent(
            type=IntentType.UNKNOWN, confidence=0.6, entities={"llm_fallback": True}
        )
