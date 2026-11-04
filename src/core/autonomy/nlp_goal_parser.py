"""
Natural Language Goal Parser - TAAK 4.1 Implementation
Advanced NLP-based goal parsing using lightweight NLP without external dependencies
ASCII-only compliance enforced
"""

import logging
import re
from typing import Any, Optional, cast

from .goal_parsers import GoalIntent, GoalParser

logger = logging.getLogger(__name__)


class NLPGoalParser(GoalParser):
    """
    Natural Language Goal Parser - TAAK 4.1
    Parses natural language goals without requiring specific prefixes
    Uses lightweight NLP techniques for ASCII-only compliance
    """

    def __init__(self) -> None:
        """Initialize NLP goal parser with pattern recognition"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Intent patterns for goal classification
        self.intent_patterns: dict[str, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
            "archive": {
                "keywords": ["save", "store", "archive", "remember", "keep", "record"],
                "patterns": [
                    r"(?:save|store|archive|remember|keep|record)\s+(.+)",
                    r"(?:can you|please|i want to|i need to)\s+(?:save|store|archive|remember|keep|record)\s+(.+)",
                    r"(?:make sure to|be sure to)\s+(?:save|store|archive|remember|keep|record)\s+(.+)",
                ],
                "goal_type": "archive",
                "capabilities": ["knowledge_management"],
                "priority": 7,
            },
            "sentiment_analysis": {
                "keywords": [
                    "sentiment",
                    "emotion",
                    "feeling",
                    "mood",
                    "analyze",
                    "opinion",
                ],
                "patterns": [
                    r"(?:analyze|check|determine|find|what is)\s+(?:the\s+)?(?:sentiment|emotion|feeling|mood)\s+(?:of|in|for)\s+(.+)",
                    r"(?:sentiment|emotion|feeling|mood)\s+(?:analysis|check|test)\s+(?:of|for)\s+(.+)",
                    r"(?:how does|what does)\s+(.+)\s+(?:feel|sound|seem)",
                ],
                "goal_type": "sentiment_analysis",
                "capabilities": ["sentiment_analysis", "text_processing"],
                "priority": 6,
            },
            "translation": {
                "keywords": ["translate", "translation", "convert", "language"],
                "patterns": [
                    r"translate\s+(.+)\s+(?:to|into)\s+(\w+)",
                    r"(?:convert|change)\s+(.+)\s+(?:to|into)\s+(\w+)(?:\s+language)?",
                    r"(?:can you|please)\s+translate\s+(.+)",
                    r"(?:what is|how do you say)\s+(.+)\s+in\s+(\w+)",
                ],
                "goal_type": "text_translation",
                "capabilities": ["text_translation", "language_processing"],
                "priority": 5,
            },
            "diagnostics": {
                "keywords": [
                    "diagnose",
                    "check",
                    "test",
                    "status",
                    "health",
                    "problem",
                    "issue",
                ],
                "patterns": [
                    r"(?:diagnose|check|test|verify)\s+(?:the\s+)?(?:system|status|health|performance)",
                    r"(?:what is|check)\s+(?:the\s+)?(?:status|health|condition)\s+(?:of|for)\s+(.+)",
                    r"(?:is there|any)\s+(?:problem|issue|error)\s+(?:with|in)\s+(.+)",
                    r"(?:run|perform)\s+(?:diagnostics|health check|system check)",
                ],
                "goal_type": "system_diagnostics",
                "capabilities": ["system_diagnostics"],
                "priority": 4,
            },
            "knowledge_search": {
                "keywords": ["find", "search", "look", "get", "retrieve", "show"],
                "patterns": [
                    r"(?:find|search|look for|get|retrieve|show me)\s+(.+)",
                    r"(?:what is|tell me about|information about)\s+(.+)",
                    r"(?:can you find|do you know)\s+(.+)",
                    r"(?:i need|looking for)\s+(?:information about|details on)\s+(.+)",
                ],
                "goal_type": "knowledge_search",
                "capabilities": ["knowledge_retrieval", "search"],
                "priority": 5,
            },
            "content_generation": {
                "keywords": ["generate", "create", "write", "make", "produce", "build"],
                "patterns": [
                    r"(?:generate|create|write|make|produce|build)\s+(?:a|an)?\s*(.+)",
                    r"(?:can you|please)\s+(?:generate|create|write|make|produce|build)\s+(.+)",
                    r"(?:i need|i want)\s+(?:a|an)?\s*(.+)\s+(?:generated|created|written|made|produced|built)",
                ],
                "goal_type": "content_generation",
                "capabilities": ["content_generation"],
                "priority": 6,
            },
        }

        # Common stop words for filtering
        self.stop_words: set[str] = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "by",
            "for",
            "from",
            "has",
            "he",
            "in",
            "is",
            "it",
            "its",
            "of",
            "on",
            "that",
            "the",
            "to",
            "was",
            "will",
            "with",
            "the",
            "this",
            "but",
            "they",
            "have",
            "had",
            "what",
            "said",
            "each",
            "which",
            "their",
            "time",
            "if",
            "up",
            "out",
            "many",
            "then",
            "them",
            "these",
            "so",
            "some",
            "her",
            "would",
            "make",
            "like",
            "into",
            "him",
            "has",
            "two",
            "more",
            "very",
            "after",
            "words",
            "long",
            "than",
            "first",
            "been",
            "call",
            "who",
            "its",
            "now",
            "find",
            "could",
            "may",
            "down",
            "side",
            "did",
            "get",
            "come",
            "made",
            "can",
            "way",
        }

        self._supported_prefixes: list[str] = []
        logger.info("NLPGoalParser initialized with pattern recognition")

    @property
    def supported_prefixes(self) -> list[str]:
        """Return supported prefixes (free-form parser uses pattern matching, not static prefixes)."""
        return list(self._supported_prefixes)

    def can_parse(self, goal_description: str) -> bool:
        """
        Check if goal can be parsed using NLP techniques

        Args:
            goal_description: Natural language goal description

        Returns:
            bool: True if goal can be parsed
        """
        if not goal_description or not goal_description.strip():
            return False

        # Skip if it's already a prefix-based goal (let existing parsers handle it)
        goal_lower = goal_description.lower().strip()
        prefix_indicators = [":", "archive:", "sentiment:", "translate:", "diagnose:"]

        for prefix in prefix_indicators:
            if prefix in goal_lower:
                return False

        # Check if goal contains recognizable intent patterns
        intent_type = self._classify_intent(goal_description)
        return intent_type is not None

    def parse(self, goal_description: str) -> GoalIntent:
        """
        Parse natural language goal description into structured intent

        Args:
            goal_description: Natural language goal description

        Returns:
            GoalIntent: Parsed goal intent

        Raises:
            ValueError: If goal cannot be parsed
        """
        try:
            intent_type = self._classify_intent(goal_description)

            if not intent_type:
                raise ValueError(f"Could not classify intent for: {goal_description}")

            intent_config = self.intent_patterns[intent_type]
            extracted_content = self._extract_content(goal_description, intent_type)
            parameters = self._extract_parameters(goal_description, intent_type, extracted_content)

            # Determine priority based on urgency indicators
            priority = self._determine_priority(goal_description, intent_config["priority"])

            # Estimate duration based on goal complexity
            estimated_duration = self._estimate_duration(goal_description, intent_type)

            self.logger.debug(
                f"NLP parsed goal type '{intent_type}' with content: {extracted_content[:50]}..."
            )

            return GoalIntent(
                goal_type=cast(str, intent_config["goal_type"]),
                content=extracted_content,
                parameters=parameters,
                required_capabilities=cast(list[str], intent_config["capabilities"]),
                priority=priority,
                estimated_duration=estimated_duration,
            )

        except Exception as e:
            self.logger.error(f"Failed to parse NLP goal '{goal_description}': {e}")
            raise ValueError(f"NLP goal parsing failed: {str(e)}")

    def validate_parameters(self, intent: GoalIntent) -> bool:
        """
        Validate parsed NLP goal intent parameters

        Args:
            intent: Parsed goal intent to validate

        Returns:
            bool: True if parameters are valid
        """
        try:
            # Check basic requirements
            if not intent.content or not intent.content.strip():
                self.logger.warning("NLP goal intent missing content")
                return False

            if not intent.goal_type:
                self.logger.warning("NLP goal intent missing goal type")
                return False

            if not intent.required_capabilities:
                self.logger.warning("NLP goal intent missing required capabilities")
                return False

            # Validate priority range
            if intent.priority < 1 or intent.priority > 10:
                self.logger.warning(f"NLP goal intent invalid priority: {intent.priority}")
                return False

            # Type-specific validation
            if intent.goal_type == "text_translation":
                if "text" not in intent.parameters:
                    self.logger.warning("Translation goal missing text parameter")
                    return False

            elif intent.goal_type == "sentiment_analysis":
                if "text" not in intent.parameters:
                    self.logger.warning("Sentiment analysis goal missing text parameter")
                    return False

            self.logger.debug("NLP goal intent validation passed")
            return True

        except Exception as e:
            self.logger.error(f"NLP goal validation failed: {e}")
            return False

    def _classify_intent(self, goal_description: str) -> str | None:
        """
        Classify goal intent using pattern matching

        Args:
            goal_description: Goal description to classify

        Returns:
            Optional[str]: Intent type or None if not classified
        """
        goal_lower = goal_description.lower().strip()

        # Score each intent type
        intent_scores: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for intent_type, raw_config in self.intent_patterns.items():
            config: dict[str, Any] = raw_config  # TODO(TYPE): replace Any with concrete type
            score = 0

            # Check for keyword matches
            for keyword in config["keywords"]:
                if keyword in goal_lower:
                    score += 2

            # Check for pattern matches
            for pattern in config["patterns"]:
                if re.search(pattern, goal_lower):
                    score += 5
                    break  # Only count one pattern match per intent

            if score > 0:
                intent_scores[intent_type] = score

        # Return highest scoring intent if above threshold
        if intent_scores:
            best_intent = max(intent_scores.items(), key=lambda x: x[1])
            if best_intent[1] >= 2:  # Minimum score threshold
                return best_intent[0]

        return None

    def _extract_content(self, goal_description: str, intent_type: str) -> str:
        """
        Extract main content from goal description

        Args:
            goal_description: Goal description
            intent_type: Classified intent type

        Returns:
            str: Extracted content
        """
        goal_lower = goal_description.lower().strip()

        # Try to extract content using patterns
        patterns = cast(list[str], self.intent_patterns[intent_type]["patterns"])

        for pattern in patterns:
            match = re.search(pattern, goal_lower)
            if match:
                # Return first capture group if available
                if match.groups():
                    content = match.group(1).strip()
                    if content:
                        return content

        # Fallback: return cleaned goal description
        return self._clean_text(goal_description)

    def _extract_parameters(
        self, goal_description: str, intent_type: str, content: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Extract intent-specific parameters

        Args:
            goal_description: Original goal description
            intent_type: Classified intent type
            content: Extracted main content

        Returns:
            Dict[str, Any]: Extracted parameters  # TODO(TYPE): replace Any with concrete type
        """
        parameters: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "action": intent_type,
            "original_text": goal_description,
            "parsed_method": "nlp",
            "metadata": {
                "source": "nlp_goal_parser",
                "parsed_at": "auto-generated",
                "confidence": self._calculate_confidence(goal_description, intent_type),
            },
        }

        # Intent-specific parameter extraction
        if intent_type == "translation":
            parameters["text"] = content

            # Try to extract target language
            lang_match = re.search(r"(?:to|into)\s+(\w+)(?:\s+language)?", goal_description.lower())
            if lang_match:
                parameters["target_language"] = lang_match.group(1).lower()
            else:
                parameters["target_language"] = "english"  # Default

            parameters["source_language"] = "auto"

        elif intent_type == "sentiment_analysis":
            parameters["text"] = content

        elif intent_type == "archive":
            parameters["type"] = "nlp_parsed_knowledge"
            parameters["confidence_score"] = 0.8

        elif intent_type == "diagnostics":
            parameters["component"] = content if content else "general"

        elif intent_type in ["knowledge_search", "content_generation"]:
            parameters["query"] = content

        return parameters

    def _determine_priority(self, goal_description: str, base_priority: int) -> int:
        """
        Determine goal priority based on urgency indicators

        Args:
            goal_description: Goal description
            base_priority: Base priority from intent type

        Returns:
            int: Adjusted priority (1-10)
        """
        goal_lower = goal_description.lower()

        # High priority indicators
        urgent_words = [
            "urgent",
            "immediately",
            "asap",
            "emergency",
            "critical",
            "now",
            "quick",
        ]
        for word in urgent_words:
            if word in goal_lower:
                return min(base_priority + 2, 10)

        # Low priority indicators
        low_priority_words = [
            "later",
            "eventually",
            "when possible",
            "sometime",
            "maybe",
        ]
        for word in low_priority_words:
            if word in goal_lower:
                return max(base_priority - 2, 1)

        return base_priority

    def _estimate_duration(self, goal_description: str, intent_type: str) -> int:
        """
        Estimate goal duration in seconds

        Args:
            goal_description: Goal description
            intent_type: Intent type

        Returns:
            int: Estimated duration in seconds
        """
        # Base durations by intent type
        base_durations = {
            "archive": 10,
            "sentiment_analysis": 5,
            "translation": 8,
            "diagnostics": 15,
            "knowledge_search": 7,
            "content_generation": 12,
        }

        base_duration = base_durations.get(intent_type, 10)

        # Adjust based on content length
        content_length = len(goal_description)
        if content_length > 200:
            return base_duration + 10
        elif content_length > 100:
            return base_duration + 5

        return base_duration

    def _calculate_confidence(self, goal_description: str, intent_type: str) -> float:
        """
        Calculate parsing confidence score

        Args:
            goal_description: Goal description
            intent_type: Classified intent type

        Returns:
            float: Confidence score (0.0-1.0)
        """
        goal_lower = goal_description.lower()

        # Base confidence
        confidence = 0.7

        # Increase confidence for exact keyword matches
        keywords = cast(list[str], self.intent_patterns[intent_type]["keywords"])
        keyword_matches = sum(1 for keyword in keywords if keyword in goal_lower)
        confidence += min(keyword_matches * 0.1, 0.2)

        # Increase confidence for pattern matches
        patterns = cast(list[str], self.intent_patterns[intent_type]["patterns"])
        for pattern in patterns:
            if re.search(pattern, goal_lower):
                confidence += 0.1
                break

        return min(confidence, 1.0)

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text

        Args:
            text: Text to clean

        Returns:
            str: Cleaned text
        """
        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", text.strip())

        # Remove common filler words from beginning
        filler_pattern = r"^(?:can you|please|i want to|i need to|could you)\s+"
        cleaned = re.sub(filler_pattern, "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()


class TemplateGoalParser(GoalParser):
    """
    Template-based Goal Parser - TAAK 4.1
    Uses regex templates for pattern matching without NLP dependencies
    """

    def __init__(self) -> None:
        """Initialize template goal parser"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Template patterns for common goal structures
        self.templates: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
            {
                "name": "analysis_template",
                "pattern": r"analyze\s+(?P<data_type>\w+)\s+from\s+(?P<source>\w+)",
                "goal_type": "analysis_goal",
                "capabilities": ["data_analysis", "source_integration"],
                "priority": 6,
                "duration": 15,
            },
            {
                "name": "generation_template",
                "pattern": r"generate\s+(?P<content_type>\w+)\s+about\s+(?P<topic>.*)",
                "goal_type": "generation_goal",
                "capabilities": ["content_generation", "knowledge_retrieval"],
                "priority": 5,
                "duration": 20,
            },
            {
                "name": "translation_template",
                "pattern": r"translate\s+(?P<text>.*)\s+to\s+(?P<language>\w+)",
                "goal_type": "translation_goal",
                "capabilities": ["text_translation", "language_processing"],
                "priority": 5,
                "duration": 8,
            },
            {
                "name": "comparison_template",
                "pattern": r"compare\s+(?P<item1>\w+)\s+(?:and|with|vs)\s+(?P<item2>\w+)",
                "goal_type": "comparison_goal",
                "capabilities": ["analysis", "comparison"],
                "priority": 6,
                "duration": 12,
            },
            {
                "name": "search_template",
                "pattern": r"(?:find|search for|look up)\s+(?P<query>.*?)(?:\s+in\s+(?P<source>\w+))?",
                "goal_type": "search_goal",
                "capabilities": ["search", "knowledge_retrieval"],
                "priority": 5,
                "duration": 7,
            },
        ]

        self._supported_prefixes: list[str] = []
        logger.info("TemplateGoalParser initialized with regex templates")

    @property
    def supported_prefixes(self) -> list[str]:
        """Return supported prefixes (template parser uses regex patterns, not static prefixes)."""
        return list(self._supported_prefixes)

    def can_parse(self, goal_description: str) -> bool:
        """
        Check if goal matches any template pattern

        Args:
            goal_description: Goal description to check

        Returns:
            bool: True if goal matches a template
        """
        if not goal_description or not goal_description.strip():
            return False

        goal_lower = goal_description.lower().strip()

        # Check each template pattern
        for template in self.templates:
            if re.search(cast(str, template["pattern"]), goal_lower, re.IGNORECASE):
                return True

        return False

    def parse(self, goal_description: str) -> GoalIntent:
        """
        Parse goal using template patterns

        Args:
            goal_description: Goal description to parse

        Returns:
            GoalIntent: Parsed goal intent

        Raises:
            ValueError: If no template matches
        """
        try:
            goal_lower = goal_description.lower().strip()

            # Find matching template
            for template in self.templates:
                match = re.search(cast(str, template["pattern"]), goal_lower, re.IGNORECASE)
                if match:
                    parameters: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                        "action": template["goal_type"],
                        "template_name": template["name"],
                        "parsed_method": "template",
                        "metadata": {
                            "source": "template_goal_parser",
                            "parsed_at": "auto-generated",
                        },
                    }

                    # Add captured groups as parameters
                    parameters.update(match.groupdict())

                    self.logger.debug(
                        f"Template parsed goal using {template['name']}: {goal_description[:50]}..."
                    )

                    return GoalIntent(
                        goal_type=template["goal_type"],
                        content=goal_description,
                        parameters=parameters,
                        required_capabilities=template["capabilities"],
                        priority=template["priority"],
                        estimated_duration=template["duration"],
                    )

            raise ValueError(f"No template pattern matched goal: {goal_description}")

        except Exception as e:
            self.logger.error(f"Failed to parse template goal '{goal_description}': {e}")
            raise ValueError(f"Template goal parsing failed: {str(e)}")

    def validate_parameters(self, intent: GoalIntent) -> bool:
        """
        Validate template-parsed goal intent

        Args:
            intent: Goal intent to validate

        Returns:
            bool: True if valid
        """
        try:
            # Basic validation
            if not intent.content or not intent.goal_type:
                return False

            # Check for template name in parameters
            if "template_name" not in intent.parameters:
                self.logger.warning("Template goal missing template_name parameter")
                return False

            # Validate template-specific requirements
            template_name = intent.parameters["template_name"]

            if template_name == "translation_template":
                if "text" not in intent.parameters or "language" not in intent.parameters:
                    return False

            elif template_name == "comparison_template":
                if "item1" not in intent.parameters or "item2" not in intent.parameters:
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Template goal validation failed: {e}")
            return False


def register_nlp_parsers() -> bool:
    """
    Register NLP and template parsers with the global registry

    Returns:
        bool: True if registration successful
    """
    from .goal_parsers import register_goal_parser

    try:
        # Register NLP parser
        nlp_parser = NLPGoalParser()
        nlp_success = register_goal_parser("nlp_parser", nlp_parser)

        # Register template parser
        template_parser = TemplateGoalParser()
        template_success = register_goal_parser("template_parser", template_parser)

        if nlp_success and template_success:
            logger.info("Successfully registered NLP and template goal parsers")
            return True
        else:
            logger.error("Failed to register some NLP goal parsers")
            return False

    except Exception as e:
        logger.error(f"Exception registering NLP goal parsers: {e}")
        return False


__all__ = ["NLPGoalParser", "TemplateGoalParser", "register_nlp_parsers"]
