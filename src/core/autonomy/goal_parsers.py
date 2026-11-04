"""
Goal Parser Infrastructure - Dynamic TaskPlanner Foundation
Implements extensible goal parsing system according to TASKPLANNER_DESIGN_SPECIFICATION.md
ASCII-only compliance enforced
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class GoalIntent(BaseModel):
    """
    Parsed goal intent structure
    Represents structured interpretation of goal description
    """

    goal_type: str = Field(description="Type of goal (archive, sentiment_analysis, etc.)")
    content: str = Field(description="Main content/text of the goal")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Goal-specific parameters")  # TODO(TYPE): replace Any with concrete type
    required_capabilities: list[str] = Field(
        default_factory=list, description="Required agent capabilities"
    )
    priority: int = Field(default=5, ge=1, le=10, description="Goal priority (1-10 scale)")
    estimated_duration: int | None = Field(
        default=None, description="Estimated duration in seconds"
    )
    goal_id: str | None = Field(default=None, description="Associated goal ID")

    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)


class GoalParser(ABC):
    """
    Abstract base class for goal parsers
    Implements extensible plugin-based goal parsing architecture
    """

    @property
    @abstractmethod
    def supported_prefixes(self) -> list[str]:
        """Return list of goal prefixes this parser handles"""

    @abstractmethod
    def can_parse(self, goal_description: str) -> bool:
        """Check if this parser can handle the goal"""

    @abstractmethod
    def parse(self, goal_description: str) -> GoalIntent:
        """Parse goal description into structured intent"""

    @abstractmethod
    def validate_parameters(self, intent: GoalIntent) -> bool:
        """Validate parsed intent has required parameters"""

    def get_parser_info(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get parser information for debugging/monitoring"""
        return {
            "parser_class": self.__class__.__name__,
            "supported_prefixes": self.supported_prefixes,
            "description": getattr(self, "__doc__", "No description available"),
        }


class GoalParserRegistry:
    """
    Registry for dynamic goal parser discovery and management
    Implements plugin-based parser registration and lookup
    """

    def __init__(self) -> None:
        self._parsers: dict[str, GoalParser] = {}
        self._prefix_map: dict[str, str] = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.info("GoalParserRegistry initialized")

    def register_parser(self, parser_id: str, parser: GoalParser) -> bool:
        """
        Register a goal parser

        Args:
            parser_id: Unique identifier for the parser
            parser: GoalParser implementation to register

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            if parser_id in self._parsers:
                self.logger.warning(f"Parser {parser_id} already registered, overwriting")

            # Validate parser
            if not isinstance(parser, GoalParser):
                raise ValueError(f"Parser must inherit from GoalParser: {type(parser)}")

            # Register parser
            self._parsers[parser_id] = parser

            # Register prefix mappings
            for prefix in parser.supported_prefixes:
                prefix_lower = prefix.lower().strip()
                if prefix_lower in self._prefix_map:
                    existing_parser = self._prefix_map[prefix_lower]
                    self.logger.warning(
                        f"Prefix '{prefix}' already mapped to parser '{existing_parser}', "
                        f"overwriting with '{parser_id}'"
                    )
                self._prefix_map[prefix_lower] = parser_id

            self.logger.info(f"Successfully registered parser: {parser_id}")
            self.logger.debug(f"Parser {parser_id} supports prefixes: {parser.supported_prefixes}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to register parser {parser_id}: {e}")
            return False

    def unregister_parser(self, parser_id: str) -> bool:
        """
        Unregister a goal parser

        Args:
            parser_id: Parser ID to unregister

        Returns:
            bool: True if unregistration successful
        """
        try:
            if parser_id not in self._parsers:
                self.logger.warning(f"Parser {parser_id} not registered")
                return False

            # Get parser to remove prefix mappings
            parser = self._parsers[parser_id]

            # Remove prefix mappings
            for prefix in parser.supported_prefixes:
                prefix_lower = prefix.lower().strip()
                if prefix_lower in self._prefix_map and self._prefix_map[prefix_lower] == parser_id:
                    del self._prefix_map[prefix_lower]

            # Remove parser
            del self._parsers[parser_id]

            self.logger.info(f"Successfully unregistered parser: {parser_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unregister parser {parser_id}: {e}")
            return False

    def find_parser(self, goal_description: str) -> GoalParser | None:
        """
        Find appropriate parser for goal description

        Args:
            goal_description: Goal description string to parse

        Returns:
            GoalParser instance or None if no parser found
        """
        if not goal_description or not goal_description.strip():
            self.logger.warning("Empty goal description provided")
            return None

        goal_lower = goal_description.lower().strip()

        # Try prefix matching first (most efficient)
        for prefix, parser_id in self._prefix_map.items():
            if goal_lower.startswith(prefix):
                parser = self._parsers.get(parser_id)
                if parser:
                    self.logger.debug(f"Found parser via prefix '{prefix}': {parser_id}")
                    return parser

        # Try can_parse method for complex matching
        for parser_id, parser in self._parsers.items():
            try:
                if parser.can_parse(goal_description):
                    self.logger.debug(f"Found parser via can_parse(): {parser_id}")
                    return parser
            except Exception as e:
                self.logger.warning(f"Parser {parser_id} can_parse() failed: {e}")

        self.logger.debug(f"No parser found for goal: {goal_description[:50]}...")
        return None

    def parse_goal(self, goal_description: str) -> GoalIntent:
        """
        Parse goal description using appropriate parser

        Args:
            goal_description: Goal description to parse

        Returns:
            GoalIntent: Parsed goal intent

        Raises:
            ValueError: If no parser found or parsing fails
        """
        parser = self.find_parser(goal_description)
        if not parser:
            supported_types = self.get_supported_goal_types()
            raise ValueError(
                f"Unsupported goal type for description: {goal_description}. "
                f"Supported types: {', '.join(supported_types)}"
            )

        try:
            intent = parser.parse(goal_description)

            if not parser.validate_parameters(intent):
                raise ValueError("Invalid parameters in parsed goal intent")

            self.logger.info(f"Successfully parsed goal: {intent.goal_type}")
            return intent

        except Exception as e:
            self.logger.error(f"Failed to parse goal '{goal_description}': {e}")
            raise ValueError(f"Goal parsing failed: {str(e)}")

    def get_supported_goal_types(self) -> list[str]:
        """
        Get list of all supported goal type prefixes

        Returns: List[Any] of supported goal type prefixes  # TODO(TYPE): replace Any with concrete type
        """
        return sorted(list(self._prefix_map.keys()))

    def get_registered_parsers(self) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get information about all registered parsers

        Returns: Dict[str, Any]ionary with parser information  # TODO(TYPE): replace Any with concrete type
        """
        return {parser_id: parser.get_parser_info() for parser_id, parser in self._parsers.items()}

    def get_parser_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get registry statistics for monitoring

        Returns: Dict[str, Any]ionary with registry statistics  # TODO(TYPE): replace Any with concrete type
        """
        return {
            "total_parsers": len(self._parsers),
            "total_prefixes": len(self._prefix_map),
            "registered_parsers": list(self._parsers.keys()),
            "supported_prefixes": self.get_supported_goal_types(),
            "registry_health": "healthy" if self._parsers else "no_parsers",
        }

    def validate_registry(self) -> bool:
        """
        Validate registry consistency

        Returns:
            bool: True if registry is consistent
        """
        try:
            # Check that all prefix mappings point to valid parsers
            for prefix, parser_id in self._prefix_map.items():
                if parser_id not in self._parsers:
                    self.logger.error(
                        f"Prefix '{prefix}' maps to non-existent parser '{parser_id}'"
                    )
                    return False

            # Check that all parsers have their prefixes mapped
            for parser_id, parser in self._parsers.items():
                for prefix in parser.supported_prefixes:
                    prefix_lower = prefix.lower().strip()
                    if prefix_lower not in self._prefix_map:
                        self.logger.error(
                            f"Parser '{parser_id}' prefix '{prefix}' not in prefix map"
                        )
                        return False

            self.logger.debug("Registry validation passed")
            return True

        except Exception as e:
            self.logger.error(f"Registry validation failed: {e}")
            return False


# Global registry instance
_global_registry: GoalParserRegistry | None = None


def get_goal_parser_registry() -> GoalParserRegistry:
    """
    Get global goal parser registry instance with auto-registration

    Returns:
        GoalParserRegistry: Global registry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = GoalParserRegistry()

        # Auto-register concrete goal parsers
        try:
            from .goal_parser_implementations import (
                ArchiveGoalParser,
                DiagnosticsGoalParser,
                SentimentGoalParser,
                TranslationGoalParser,
            )

            # Register all concrete parsers
            parsers = [
                ("archive_parser", ArchiveGoalParser()),
                ("sentiment_parser", SentimentGoalParser()),
                ("translation_parser", TranslationGoalParser()),
                ("diagnostics_parser", DiagnosticsGoalParser()),
            ]

            for parser_id, parser in parsers:
                success = _global_registry.register_parser(parser_id, parser)
                if success:
                    logger.info(f"Auto-registered goal parser: {parser_id}")
                else:
                    logger.warning(f"Failed to auto-register goal parser: {parser_id}")

            # Auto-register NLP parsers - TAAK 4.1 Integration
            try:
                from .nlp_goal_parser import NLPGoalParser, TemplateGoalParser

                nlp_parsers = [
                    ("nlp_parser", NLPGoalParser()),
                    ("template_parser", TemplateGoalParser()),
                ]

                for parser_id, parser in nlp_parsers:
                    success = _global_registry.register_parser(parser_id, parser)
                    if success:
                        logger.info(f"Auto-registered NLP goal parser: {parser_id}")
                        parsers.append((parser_id, parser))
                    else:
                        logger.warning(f"Failed to auto-register NLP goal parser: {parser_id}")

            except ImportError as e:
                logger.warning(f"NLP goal parsers not available: {e}")
            except Exception as e:
                logger.error(f"Error registering NLP goal parsers: {e}")

            logger.info(f"Goal parser registry initialized with {len(parsers)} parsers")

        except ImportError as e:
            logger.warning(f"Could not auto-register goal parsers: {e}")

    return _global_registry


def register_goal_parser(parser_id: str, parser: GoalParser) -> bool:
    """
    Convenience function to register parser with global registry

    Args:
        parser_id: Unique parser identifier
        parser: GoalParser implementation

    Returns:
        bool: Registration success
    """
    registry = get_goal_parser_registry()
    return registry.register_parser(parser_id, parser)


def parse_goal_description(goal_description: str) -> GoalIntent:
    """
    Convenience function to parse goal using global registry

    Args:
        goal_description: Goal description to parse

    Returns:
        GoalIntent: Parsed goal intent
    """
    registry = get_goal_parser_registry()
    return registry.parse_goal(goal_description)


__all__ = [
    "GoalIntent",
    "GoalParser",
    "GoalParserRegistry",
    "get_goal_parser_registry",
    "register_goal_parser",
    "parse_goal_description",
]
