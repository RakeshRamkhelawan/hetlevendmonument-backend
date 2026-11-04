"""Natural Language Processing for Scheduling.

This module provides NLP capabilities for understanding scheduling-related
natural language queries and commands.
"""

from src.core.scheduling.nlp.context import ContextManager, ConversationContext
from src.core.scheduling.nlp.entities import EntityExtractor, ExtractedEntity
from src.core.scheduling.nlp.intents import ClassifiedIntent, IntentClassifier, IntentType
from src.core.scheduling.nlp.parser import NaturalLanguageParser, ParsedSchedulingRequest

__all__ = [
    "ConversationContext",
    "ContextManager",
    "ExtractedEntity",
    "EntityExtractor",
    "ClassifiedIntent",
    "IntentClassifier",
    "IntentType",
    "NaturalLanguageParser",
    "ParsedSchedulingRequest",
]
