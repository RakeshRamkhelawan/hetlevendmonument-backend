"""Intent classification for scheduling natural language.

Uses pattern matching and keyword analysis to classify user intents.
Future: Can be enhanced with ML-based classification.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum, auto

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Types of scheduling intents."""

    SCHEDULE = auto()  # Create a new meeting
    RESCHEDULE = auto()  # Move an existing meeting
    CANCEL = auto()  # Cancel a meeting
    QUERY_AVAILABILITY = auto()  # Check when someone is free
    QUERY_CONFLICTS = auto()  # Check for conflicts
    LIST_EVENTS = auto()  # Show my meetings
    UPDATE = auto()  # Update meeting details
    UNKNOWN = auto()  # Could not determine intent


@dataclass
class ClassifiedIntent:
    """Result of intent classification."""

    intent_type: IntentType
    confidence: float  # 0.0 to 1.0
    matched_keywords: list[str]
    original_text: str


class IntentClassifier:
    """Classifies natural language into scheduling intents.

    Uses keyword-based classification with confidence scoring.
    Patterns are ordered by specificity to reduce ambiguity.
    """

    # Keyword patterns for each intent - ordered from most to least specific
    INTENT_PATTERNS: dict[IntentType, list[str]] = {
        IntentType.SCHEDULE: [
            # High specificity patterns first
            r"\b(schedule|book|set up|arrange|plan|create|new)\s+(a\s+)?(meeting|call|appointment|sync|chat|discussion|interview)\b",
            r"\b(let\s+'?\s*\s+meet|can\s+we\s+meet|available\s+for\s+a\s+meeting)\b",
            r"\bfind\s+(a\s+)?time\s+(for|to)\b",
            r"\b(put\s+on\s+(my\s+)?calendar|add\s+to\s+(my\s+)?schedule)\b",
            r"\bset\s+up\s+a\s+(time|meeting|call)\b",
            r"\barrange\s+a\s+(meeting|call|get-together)\b",
        ],
        IntentType.RESCHEDULE: [
            # Clear rescheduling patterns
            r"\b(reschedule|move|shift)\s+(the\s+)?(meeting|call|appointment|event)\b",
            r"\breschedule\b",
            r"\bmove\s+(the\s+)?\w+\s+to\b",
            r"\bchange\s+(the\s+)?(time|date|day)\s+(of|for)\b",
            r"\b(cannot\s+make\s+it|can\s+not\s+make\s+it|won'?t\s+work|need\s+to\s+change|different\s+time)\b",
            r"\b(push|bump)\s+(the\s+)?(meeting|call)\s+(to|until|back)\b",
            r"\b(let'?s\s+(do|try)|how\s+about)\s+(\w+\s+)?(instead|tomorrow|next|another)\b",
            r"\bmove\s+(the\s+)?(meeting|call)\s+(to|from)\b",
        ],
        IntentType.CANCEL: [
            # Clear cancellation patterns
            r"\b(cancel|call\s+off|scrap|abort)\s+(the\s+)?(meeting|call|appointment|event)\b",
            r"\b(we\s+need\s+to\s+cancel|let'?s\s+cancel|I\s+need\s+to\s+cancel)\b",
            r"\b(remove|delete)\s+(the\s+)?(meeting|event|appointment)\s+(from\s+)?(my\s+)?(calendar|schedule)\b",
            r"\b(won'?t\s+be\s+able\s+to\s+make\s+it|can'?t\s+make\s+it|unable\s+to\s+attend)\b",
            r"\b(nevermind|never\s+mind|forget\s+(about\s+)?(the\s+)?meeting)\b",
            r"\bcall\s+(off|the\s+meeting)\b",
        ],
        IntentType.QUERY_AVAILABILITY: [
            # Availability queries
            r"\bwhen\s+(is|are)\s+\w+\s+(available|free|open)\b",
            r"\bfind\s+(a\s+)?time\s+(when|that)\b",
            r"\b(what\s+time\s+works|good\s+time\s+for|best\s+time)\b",
            r"\b(show\s+me\s+)?\w+\s+(availability|schedule|calendar)\b",
            r"\b(is|are)\s+\w+\s+free\s+(on|at|tomorrow|next)\b",
            r"\bwhen\s+(can|could)\s+we\s+meet\b",
            r"\bwhat\s+times?\s+(are\s+available|work)\b",
        ],
        IntentType.QUERY_CONFLICTS: [
            # Conflict detection
            r"\b(conflicts?|overlaps?|double\s+booked|collision)\b",
            r"\b(do\s+I\s+have\s+(any\s+)?conflicts|will\s+this\s+conflict)\b",
            r"\b(am\s+I\s+free|do\s+I\s+have\s+time|is\s+this\s+slot\s+free)\b",
            r"\bdoes\s+this\s+(conflict|overlap)\b",
            r"\bcheck\s+(for\s+)?conflicts\b",
            r"\bwill\s+I\s+be\s+double\s+booked\b",
        ],
        IntentType.LIST_EVENTS: [
            # Listing events
            r"\b(show|list|view|display)\s+(me\s+)?(my\s+)?(upcoming\s+)?(meetings?|events?|appointments?)\b",
            r"\b(my\s+(upcoming|next)\s+(meetings?|events?|appointments?))\b",
            r"\bwhat\s+do\s+I\s+have\s+(on|tomorrow|next|this)\b",
            r"\bwhat'?s\s+on\s+my\s+(calendar|schedule|agenda)\b",
            r"\b(agenda|calendar|schedule)\s+(for\s+)?(today|tomorrow|this\s+week|next\s+week)\b",
            r"\bshow\s+me\s+what\s+I\s+have\b",
        ],
        IntentType.UPDATE: [
            # Update/modify patterns
            r"\b(update|change|modify|edit)\s+(the\s+)?(title|time|date|location|duration|length)\s+(of\s+)?(the\s+)?(meeting|call|event)\b",
            r"\b(change|update|modify|edit)\s+(the\s+)?(title|name|topic|subject|description)\b",
            r"\b(add|remove)\s+(a\s+)?(participant|attendee|person)\s+(to|from)\b",
            r"\b(make\s+it\s+(longer|shorter)|extend|shorten)\s+(the\s+)?(meeting|duration)\b",
            r"\bset\s+(the\s+)?(title|topic|subject)\s+(to|as)\b",
            r"\b(move\s+the\s+location|change\s+the\s+place)\b",
            r"\bupdate\s+(the\s+)?meeting\s+details\b",
        ],
    }

    def __init__(self) -> None:
        """Initialize the intent classifier with compiled patterns."""
        self._patterns: dict[IntentType, list[re.Pattern[str]]] = {}
        for intent_type, patterns in self.INTENT_PATTERNS.items():
            self._patterns[intent_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def classify(self, text: str) -> ClassifiedIntent:
        """Classify the intent of the given text.

        Args:
            text: Natural language input to classify

        Returns:
            ClassifiedIntent with type, confidence, and matched keywords
        """
        if not text or not text.strip():
            return ClassifiedIntent(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                matched_keywords=[],
                original_text=text,
            )

        text_lower = text.lower().strip()
        scores: dict[IntentType, float] = {}
        matched_keywords: dict[IntentType, list[str]] = {}

        # Score each intent based on pattern matches
        for intent_type, patterns in self._patterns.items():
            score = 0.0
            matches: list[str] = []

            for pattern in patterns:
                match = pattern.search(text_lower)
                if match:
                    # Calculate match quality based on pattern position
                    # Earlier matches in the text get higher scores
                    position_weight = 1.0 - (match.start() / len(text_lower)) * 0.3
                    score += 1.0 * position_weight
                    matches.append(match.group(0))

            if score > 0:
                scores[intent_type] = score
                matched_keywords[intent_type] = matches

        # Determine the best intent
        if not scores:
            return ClassifiedIntent(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                matched_keywords=[],
                original_text=text,
            )

        # Get the intent with highest score
        best_intent = max(scores, key=lambda k: scores.get(k, 0))
        best_score = scores[best_intent]

        # Calculate confidence (normalize by number of patterns for that intent)
        total_patterns = len(self._patterns[best_intent])
        confidence = min(1.0, best_score / max(1, total_patterns * 0.3))

        # Boost confidence for exact keyword matches
        exact_match_boost = self._calculate_exact_match_boost(text_lower, best_intent)
        confidence = min(1.0, confidence + exact_match_boost)

        # Reduce confidence if multiple intents have similar scores
        if len(scores) > 1:
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2:
                score_diff = sorted_scores[0] - sorted_scores[1]
                if score_diff < 0.5:
                    # Ambiguous - reduce confidence
                    confidence *= 0.8

        logger.debug(
            f"Classified '{text[:50]}...' as {best_intent.name} with confidence {confidence:.2f}"
        )

        return ClassifiedIntent(
            intent_type=best_intent,
            confidence=confidence,
            matched_keywords=matched_keywords.get(best_intent, []),
            original_text=text,
        )

    def _calculate_exact_match_boost(self, text: str, intent_type: IntentType) -> float:
        """Calculate confidence boost for exact keyword matches.

        Args:
            text: Lowercase text to check
            intent_type: Intent type to check against

        Returns:
            Confidence boost value (0.0 to 0.3)
        """
        exact_keywords: dict[IntentType, set[str]] = {
            IntentType.SCHEDULE: {
                "schedule",
                "book",
                "set up",
                "arrange",
                "new meeting",
                "create a meeting",
            },
            IntentType.RESCHEDULE: {
                "reschedule",
                "move",
                "shift",
                "change the time",
                "different time",
            },
            IntentType.CANCEL: {
                "cancel",
                "call off",
                "delete",
                "won't make it",
                "can't make it",
            },
            IntentType.QUERY_AVAILABILITY: {
                "available",
                "free",
                "when",
                "what time works",
            },
            IntentType.QUERY_CONFLICTS: {
                "conflict",
                "overlap",
                "double booked",
            },
            IntentType.LIST_EVENTS: {
                "show me",
                "my meetings",
                "calendar",
                "what do i have",
            },
            IntentType.UPDATE: {
                "update",
                "change",
                "modify",
                "edit",
                "add participant",
                "remove participant",
            },
        }

        keywords = exact_keywords.get(intent_type, set())
        matched_keywords = [kw for kw in keywords if kw in text]

        # Boost based on number of exact matches (max 0.3)
        return min(0.3, len(matched_keywords) * 0.1)

    def get_alternative_intents(self, text: str, top_k: int = 3) -> list[ClassifiedIntent]:
        """Get alternative intent classifications.

        Args:
            text: Natural language input
            top_k: Number of alternatives to return

        Returns:
            List of ClassifiedIntent sorted by confidence
        """
        all_intents: list[ClassifiedIntent] = []

        # Re-classify for all intents
        text_lower = text.lower().strip()

        for intent_type in IntentType:
            if intent_type == IntentType.UNKNOWN:
                continue

            patterns = self._patterns.get(intent_type, [])
            score = 0.0
            matches: list[str] = []

            for pattern in patterns:
                match = pattern.search(text_lower)
                if match:
                    position_weight = 1.0 - (match.start() / len(text_lower)) * 0.3
                    score += 1.0 * position_weight
                    matches.append(match.group(0))

            if score > 0:
                total_patterns = len(patterns) if patterns else 1
                confidence = min(1.0, score / max(1, total_patterns * 0.3))

                # Add exact match boost
                exact_boost = self._calculate_exact_match_boost(text_lower, intent_type)
                confidence = min(1.0, confidence + exact_boost)

                all_intents.append(
                    ClassifiedIntent(
                        intent_type=intent_type,
                        confidence=confidence,
                        matched_keywords=matches,
                        original_text=text,
                    )
                )

        # Sort by confidence and return top_k
        all_intents.sort(key=lambda x: x.confidence, reverse=True)
        return all_intents[:top_k]
