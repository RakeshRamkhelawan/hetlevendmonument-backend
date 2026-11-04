"""
Concrete Goal Parser Implementations
Implements specific parsers for each goal type according to TASKPLANNER_DESIGN_SPECIFICATION.md
ASCII-only compliance enforced
"""

import logging
import re

from .goal_parsers import GoalIntent, GoalParser

logger = logging.getLogger(__name__)


class ArchiveGoalParser(GoalParser):
    """
    Parser for archive: goal types
    Handles knowledge archival goals for backward compatibility
    """

    @property
    def supported_prefixes(self) -> list[str]:
        return ["archive:"]

    def can_parse(self, goal_description: str) -> bool:
        """Check if goal can be parsed as archive goal"""
        return goal_description.strip().lower().startswith("archive:")

    def parse(self, goal_description: str) -> GoalIntent:
        """Parse archive goal description into structured intent"""
        try:
            # Remove "archive:" prefix
            content = goal_description[8:].strip()

            if not content:
                raise ValueError("Archive goal must contain content after 'archive:' prefix")

            logger.debug(f"Parsing archive goal with content: {content[:50]}...")

            return GoalIntent(
                goal_type="archive",
                content=content,
                parameters={
                    "action": "create_knowledge",
                    "type": "archived_goal",
                    "confidence_score": 0.9,
                    "metadata": {
                        "source": "archive_goal_parser",
                        "parsed_at": "auto-generated",
                    },
                },
                required_capabilities=["knowledge_management"],
                priority=7,
                estimated_duration=10,
            )

        except Exception as e:
            logger.error(f"Failed to parse archive goal '{goal_description}': {e}")
            raise ValueError(f"Invalid archive goal format: {str(e)}")

    def validate_parameters(self, intent: GoalIntent) -> bool:
        """Validate archive goal intent parameters"""
        try:
            # Check required fields
            if not intent.content:
                logger.warning("Archive goal intent missing content")
                return False

            if intent.goal_type != "archive":
                logger.warning(f"Expected archive goal type, got: {intent.goal_type}")
                return False

            # Check required parameters
            required_params = ["action", "type", "confidence_score"]
            for param in required_params:
                if param not in intent.parameters:
                    logger.warning(f"Archive goal missing required parameter: {param}")
                    return False

            # Validate action
            if intent.parameters.get("action") != "create_knowledge":
                logger.warning(
                    f"Invalid action for archive goal: {intent.parameters.get('action')}"
                )
                return False

            logger.debug("Archive goal intent validation passed")
            return True

        except Exception as e:
            logger.error(f"Archive goal validation failed: {e}")
            return False


class SentimentGoalParser(GoalParser):
    """
    Parser for analyze_sentiment: goal types
    Handles sentiment analysis goals
    """

    @property
    def supported_prefixes(self) -> list[str]:
        return ["analyze_sentiment:", "sentiment_analysis:", "sentiment:"]

    def can_parse(self, goal_description: str) -> bool:
        """Check if goal can be parsed as sentiment analysis goal"""
        goal_lower = goal_description.strip().lower()
        return any(goal_lower.startswith(prefix) for prefix in self.supported_prefixes)

    def parse(self, goal_description: str) -> GoalIntent:
        """Parse sentiment analysis goal description into structured intent"""
        try:
            # Find the prefix used
            goal_lower = goal_description.lower().strip()
            used_prefix = None
            for prefix in self.supported_prefixes:
                if goal_lower.startswith(prefix):
                    used_prefix = prefix
                    break

            if not used_prefix:
                raise ValueError(f"Invalid sentiment goal format: {goal_description}")

            # Extract text to analyze
            text = goal_description[len(used_prefix) :].strip()

            if not text:
                raise ValueError("Sentiment analysis goal must contain text to analyze")

            logger.debug(f"Parsing sentiment goal with text: {text[:50]}...")

            return GoalIntent(
                goal_type="sentiment_analysis",
                content=text,
                parameters={
                    "action": "sentiment_analysis",
                    "text": text,
                    "metadata": {
                        "source": "sentiment_goal_parser",
                        "parsed_at": "auto-generated",
                    },
                },
                required_capabilities=["sentiment_analysis", "text_processing"],
                priority=6,
                estimated_duration=5,
            )

        except Exception as e:
            logger.error(f"Failed to parse sentiment goal '{goal_description}': {e}")
            raise ValueError(f"Invalid sentiment goal format: {str(e)}")

    def validate_parameters(self, intent: GoalIntent) -> bool:
        """Validate sentiment analysis goal intent parameters"""
        try:
            # Check required fields
            if not intent.content:
                logger.warning("Sentiment goal intent missing content")
                return False

            if intent.goal_type != "sentiment_analysis":
                logger.warning(f"Expected sentiment_analysis goal type, got: {intent.goal_type}")
                return False

            # Check required parameters
            if not intent.parameters.get("text"):
                logger.warning("Sentiment goal missing required text parameter")
                return False

            # Validate action
            if intent.parameters.get("action") != "sentiment_analysis":
                logger.warning(
                    f"Invalid action for sentiment goal: {intent.parameters.get('action')}"
                )
                return False

            logger.debug("Sentiment goal intent validation passed")
            return True

        except Exception as e:
            logger.error(f"Sentiment goal validation failed: {e}")
            return False


class TranslationGoalParser(GoalParser):
    """
    Parser for translate_text: goal types
    Handles text translation goals for new Translation Agent
    """

    @property
    def supported_prefixes(self) -> list[str]:
        return ["translate_text:", "translate:", "translation:"]

    def can_parse(self, goal_description: str) -> bool:
        """Check if goal can be parsed as translation goal"""
        goal_lower = goal_description.strip().lower()
        return any(goal_lower.startswith(prefix) for prefix in self.supported_prefixes)

    def parse(self, goal_description: str) -> GoalIntent:
        """Parse translation goal description into structured intent"""
        try:
            # Find the prefix used
            goal_lower = goal_description.lower().strip()
            used_prefix = None
            for prefix in self.supported_prefixes:
                if goal_lower.startswith(prefix):
                    used_prefix = prefix
                    break

            if not used_prefix:
                raise ValueError(f"Invalid translation goal format: {goal_description}")

            # Extract text and parse optional language specification
            remaining_text = goal_description[len(used_prefix) :].strip()

            if not remaining_text:
                raise ValueError("Translation goal must contain text to translate")

            # Parse optional target language
            # Format: "translate_text: Hello world [to:dutch]"
            target_language = "english"  # Default
            text = remaining_text

            # Look for language specification
            language_pattern = r"\[to:([a-zA-Z]+)\]"
            language_match = re.search(language_pattern, remaining_text)

            if language_match:
                target_language = language_match.group(1).lower()
                # Remove language specification from text
                text = re.sub(language_pattern, "", remaining_text).strip()

            if not text:
                raise ValueError("Translation goal must contain text after language specification")

            logger.debug(f"Parsing translation goal: '{text[:30]}...' to {target_language}")

            return GoalIntent(
                goal_type="text_translation",
                content=text,
                parameters={
                    "action": "translate_text",
                    "text": text,
                    "target_language": target_language,
                    "source_language": "auto",  # Auto-detect source language
                    "metadata": {
                        "source": "translation_goal_parser",
                        "parsed_at": "auto-generated",
                    },
                },
                required_capabilities=["text_translation", "language_processing"],
                priority=5,
                estimated_duration=8,
            )

        except Exception as e:
            logger.error(f"Failed to parse translation goal '{goal_description}': {e}")
            raise ValueError(f"Invalid translation goal format: {str(e)}")

    def validate_parameters(self, intent: GoalIntent) -> bool:
        """Validate translation goal intent parameters"""
        try:
            # Check required fields
            if not intent.content:
                logger.warning("Translation goal intent missing content")
                return False

            if intent.goal_type != "text_translation":
                logger.warning(f"Expected text_translation goal type, got: {intent.goal_type}")
                return False

            # Check required parameters
            required_params = ["text", "target_language"]
            for param in required_params:
                if not intent.parameters.get(param):
                    logger.warning(f"Translation goal missing required parameter: {param}")
                    return False

            # Validate action
            if intent.parameters.get("action") != "translate_text":
                logger.warning(
                    f"Invalid action for translation goal: {intent.parameters.get('action')}"
                )
                return False

            # Validate target language format
            target_lang = intent.parameters.get("target_language", "").lower()
            if not target_lang.isalpha():
                logger.warning(f"Invalid target language format: {target_lang}")
                return False

            logger.debug("Translation goal intent validation passed")
            return True

        except Exception as e:
            logger.error(f"Translation goal validation failed: {e}")
            return False


class DiagnosticsGoalParser(GoalParser):
    """
    Parser for diagnose_system: goal types
    Handles system diagnostics goals
    """

    @property
    def supported_prefixes(self) -> list[str]:
        return ["diagnose_system:", "diagnose:", "system_check:", "diagnostics:"]

    def can_parse(self, goal_description: str) -> bool:
        """Check if goal can be parsed as diagnostics goal"""
        goal_lower = goal_description.strip().lower()
        return any(goal_lower.startswith(prefix) for prefix in self.supported_prefixes)

    def parse(self, goal_description: str) -> GoalIntent:
        """Parse diagnostics goal description into structured intent"""
        try:
            # Find the prefix used
            goal_lower = goal_description.lower().strip()
            used_prefix = None
            for prefix in self.supported_prefixes:
                if goal_lower.startswith(prefix):
                    used_prefix = prefix
                    break

            if not used_prefix:
                raise ValueError(f"Invalid diagnostics goal format: {goal_description}")

            # Extract component specification
            component = goal_description[len(used_prefix) :].strip()

            # Default to "general" if no specific component specified
            if not component:
                component = "general"

            logger.debug(f"Parsing diagnostics goal for component: {component}")

            return GoalIntent(
                goal_type="system_diagnostics",
                content=component,
                parameters={
                    "action": "diagnose_system",
                    "component": component,
                    "metadata": {
                        "source": "diagnostics_goal_parser",
                        "parsed_at": "auto-generated",
                    },
                },
                required_capabilities=["system_diagnostics"],
                priority=4,
                estimated_duration=15,
            )

        except Exception as e:
            logger.error(f"Failed to parse diagnostics goal '{goal_description}': {e}")
            raise ValueError(f"Invalid diagnostics goal format: {str(e)}")

    def validate_parameters(self, intent: GoalIntent) -> bool:
        """Validate diagnostics goal intent parameters"""
        try:
            # Check required fields
            if not intent.content:
                logger.warning("Diagnostics goal intent missing content")
                return False

            if intent.goal_type != "system_diagnostics":
                logger.warning(f"Expected system_diagnostics goal type, got: {intent.goal_type}")
                return False

            # Check required parameters
            if not intent.parameters.get("component"):
                logger.warning("Diagnostics goal missing required component parameter")
                return False

            # Validate action
            if intent.parameters.get("action") != "diagnose_system":
                logger.warning(
                    f"Invalid action for diagnostics goal: {intent.parameters.get('action')}"
                )
                return False

            # Validate component format (basic validation)
            component = intent.parameters.get("component", "")
            if not component or not isinstance(component, str):
                logger.warning(f"Invalid component specification: {component}")
                return False

            logger.debug("Diagnostics goal intent validation passed")
            return True

        except Exception as e:
            logger.error(f"Diagnostics goal validation failed: {e}")
            return False


def register_all_parsers() -> bool:
    """
    Register all concrete goal parser implementations with global registry

    Returns:
        bool: True if all parsers registered successfully
    """
    from .goal_parsers import register_goal_parser

    parsers = [
        ("archive", ArchiveGoalParser()),
        ("sentiment", SentimentGoalParser()),
        ("translation", TranslationGoalParser()),
        ("diagnostics", DiagnosticsGoalParser()),
    ]

    success_count = 0
    total_count = len(parsers)

    for parser_id, parser_instance in parsers:
        try:
            if register_goal_parser(parser_id, parser_instance):
                success_count += 1
                logger.info(f"Successfully registered {parser_id} parser")
            else:
                logger.error(f"Failed to register {parser_id} parser")
        except Exception as e:
            logger.error(f"Exception registering {parser_id} parser: {e}")

    logger.info(f"Goal parser registration: {success_count}/{total_count} successful")
    return success_count == total_count


__all__ = [
    "ArchiveGoalParser",
    "SentimentGoalParser",
    "TranslationGoalParser",
    "DiagnosticsGoalParser",
    "register_all_parsers",
]
