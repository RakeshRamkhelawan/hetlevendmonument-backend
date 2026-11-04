"""
Intent Classification System - TAAK 4.1 Implementation
Lightweight intent classification without external ML dependencies
ASCII-only compliance enforced
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IntentClassificationResult:
    """
    Result of intent classification with confidence and metadata
    """

    def __init__(
        self,
        intent_type: str,
        confidence: float,
        features: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.intent_type = intent_type
        self.confidence = confidence
        self.features = features
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert result to dictionary"""
        return {
            "intent_type": self.intent_type,
            "confidence": self.confidence,
            "features": self.features,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class CapabilityMapper:
    """
    Maps goal intents to required agent capabilities
    """

    def __init__(self) -> None:
        """Initialize capability mapper with predefined mappings"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Capability mappings for goal types
        self.capability_mappings: dict[str, list[str]] = {
            "archive": ["knowledge_management", "data_storage"],
            "sentiment_analysis": ["sentiment_analysis", "text_processing", "nlp"],
            "text_translation": ["text_translation", "language_processing", "nlp"],
            "system_diagnostics": ["system_diagnostics", "monitoring", "health_check"],
            "knowledge_search": ["knowledge_retrieval", "search", "data_access"],
            "content_generation": [
                "content_generation",
                "text_generation",
                "creativity",
            ],
            "analysis_goal": ["data_analysis", "analytical_reasoning"],
            "comparison_goal": ["comparison", "analytical_reasoning", "evaluation"],
            "search_goal": ["search", "information_retrieval", "data_access"],
            "generation_goal": ["content_generation", "creative_writing"],
        }

        # Entity type to capability mappings
        self.entity_capability_mappings: dict[str, list[str]] = {
            "FILE": ["file_management", "data_access"],
            "URL": ["web_access", "data_retrieval"],
            "EMAIL": ["communication", "email_processing"],
            "DATE": ["temporal_reasoning", "scheduling"],
            "NUMBER": ["mathematical_processing", "calculation"],
            "PERSON": ["entity_recognition", "social_context"],
            "ORGANIZATION": ["entity_recognition", "business_context"],
            "LOCATION": ["geographic_reasoning", "location_services"],
        }

        logger.info("CapabilityMapper initialized with predefined mappings")

    def map_intent_to_capabilities(self, intent_type: str) -> list[str]:
        """
        Map intent type to required capabilities

        Args:
            intent_type: Goal intent type

        Returns:
            List[str]: Required capabilities
        """
        capabilities = self.capability_mappings.get(intent_type, [])
        self.logger.debug(f"Mapped intent '{intent_type}' to capabilities: {capabilities}")
        return capabilities.copy()

    def map_entities_to_capabilities(self, entities: list[tuple[str, str]]) -> list[str]:
        """
        Map detected entities to additional capabilities

        Args:
            entities: List[Any] of (entity_text, entity_type) tuples  # TODO(TYPE): replace Any with concrete type

        Returns:
            List[str]: Additional capabilities based on entities
        """
        additional_capabilities = set()

        for entity_text, entity_type in entities:
            capabilities = self.entity_capability_mappings.get(entity_type, [])
            additional_capabilities.update(capabilities)

        result = list(additional_capabilities)
        self.logger.debug(f"Mapped {len(entities)} entities to capabilities: {result}")
        return result

    def suggest_capabilities(self, text: str, intent_type: str | None = None) -> list[str]:
        """
        Suggest capabilities based on text analysis

        Args:
            text: Text to analyze
            intent_type: Optional known intent type

        Returns:
            List[str]: Suggested capabilities
        """
        capabilities = set()

        # Add base capabilities for intent type
        if intent_type:
            capabilities.update(self.map_intent_to_capabilities(intent_type))

        # Analyze text for capability indicators
        text_lower = text.lower()

        # File processing indicators
        if any(keyword in text_lower for keyword in ["file", "document", "pdf", "csv", "json"]):
            capabilities.add("file_processing")

        # Web processing indicators
        if any(keyword in text_lower for keyword in ["url", "website", "web", "http", "download"]):
            capabilities.add("web_access")

        # Database indicators
        if any(
            keyword in text_lower for keyword in ["database", "sql", "query", "table", "record"]
        ):
            capabilities.add("database_access")

        # Communication indicators
        if any(
            keyword in text_lower for keyword in ["email", "send", "notify", "message", "alert"]
        ):
            capabilities.add("communication")

        # Mathematical indicators
        if any(
            keyword in text_lower for keyword in ["calculate", "math", "number", "sum", "average"]
        ):
            capabilities.add("mathematical_processing")

        return list(capabilities)


class LightweightIntentClassifier:
    """
    Lightweight intent classifier using pattern matching and feature extraction
    No external ML dependencies required
    """

    def __init__(self, model_path: str | None = None) -> None:
        """
        Initialize intent classifier

        Args:
            model_path: Optional path to load classification model
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.capability_mapper = CapabilityMapper()

        # Classification features and weights
        self.feature_weights: dict[str, float] = {
            "keyword_match": 0.4,
            "pattern_match": 0.3,
            "entity_presence": 0.2,
            "length_factor": 0.1,
        }

        # Intent classification patterns
        self.intent_classifiers: dict[str, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
            "archive": {
                "keywords": [
                    "save",
                    "store",
                    "archive",
                    "remember",
                    "keep",
                    "record",
                    "backup",
                ],
                "patterns": [
                    r"(?:save|store|archive|remember|keep|record)\s+.*",
                    r".*(?:for later|to remember|in memory).*",
                ],
                "entities": ["FILE", "URL"],
                "priority": 7,
            },
            "sentiment_analysis": {
                "keywords": [
                    "sentiment",
                    "emotion",
                    "feeling",
                    "mood",
                    "opinion",
                    "analyze",
                ],
                "patterns": [
                    r".*sentiment.*",
                    r".*(?:how.*feel|what.*think|opinion about).*",
                ],
                "entities": ["PERSON"],
                "priority": 6,
            },
            "text_translation": {
                "keywords": ["translate", "translation", "convert", "language"],
                "patterns": [r"translate.*to\s+\w+", r".*in\s+\w+\s+language.*"],
                "entities": [],
                "priority": 5,
            },
            "system_diagnostics": {
                "keywords": [
                    "diagnose",
                    "check",
                    "test",
                    "status",
                    "health",
                    "problem",
                    "debug",
                ],
                "patterns": [
                    r".*(?:system|status|health|performance).*",
                    r".*(?:problem|issue|error|bug).*",
                ],
                "entities": [],
                "priority": 8,
            },
            "knowledge_search": {
                "keywords": [
                    "find",
                    "search",
                    "look",
                    "get",
                    "retrieve",
                    "show",
                    "information",
                ],
                "patterns": [
                    r"(?:find|search|look for|get|retrieve|show).*",
                    r".*(?:what is|tell me about|information about).*",
                ],
                "entities": ["ORGANIZATION", "LOCATION"],
                "priority": 5,
            },
            "content_generation": {
                "keywords": [
                    "generate",
                    "create",
                    "write",
                    "make",
                    "produce",
                    "build",
                    "compose",
                ],
                "patterns": [
                    r"(?:generate|create|write|make|produce|build|compose).*",
                    r".*(?:report|document|article|summary).*",
                ],
                "entities": [],
                "priority": 6,
            },
        }

        logger.info("LightweightIntentClassifier initialized")

    def classify_intent(self, text: str) -> IntentClassificationResult:
        """
        Classify intent of given text

        Args:
            text: Text to classify

        Returns:
            IntentClassificationResult: Classification result with confidence
        """
        try:
            if not text or not text.strip():
                return IntentClassificationResult(
                    intent_type="unknown",
                    confidence=0.0,
                    features={"error": "empty_text"},
                    metadata={"classifier": "lightweight"},
                )

            # Extract features
            features = self._extract_features(text)

            # Score each intent type
            intent_scores: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for intent_type, classifier_config in self.intent_classifiers.items():
                score = self._calculate_intent_score(features, classifier_config)
                if score > 0:
                    intent_scores[intent_type] = score

            # Determine best intent
            if intent_scores:
                best_intent = max(intent_scores.items(), key=lambda x: x[1])
                intent_type, confidence = best_intent

                # Normalize confidence to 0-1 range
                confidence = min(confidence / 10.0, 1.0)

                self.logger.debug(
                    f"Classified intent '{intent_type}' with confidence {confidence:.2f}"
                )

                return IntentClassificationResult(
                    intent_type=intent_type,
                    confidence=confidence,
                    features=features,
                    metadata={
                        "classifier": "lightweight",
                        "all_scores": intent_scores,
                        "text_length": len(text),
                    },
                )
            else:
                return IntentClassificationResult(
                    intent_type="unknown",
                    confidence=0.0,
                    features=features,
                    metadata={
                        "classifier": "lightweight",
                        "reason": "no_pattern_match",
                    },
                )

        except Exception as e:
            self.logger.error(f"Intent classification failed: {e}")
            return IntentClassificationResult(
                intent_type="error",
                confidence=0.0,
                features={"error": str(e)},
                metadata={"classifier": "lightweight"},
            )

    def get_suggested_capabilities(self, text: str, intent_type: str | None = None) -> list[str]:
        """
        Get suggested capabilities for text and intent

        Args:
            text: Text to analyze
            intent_type: Optional known intent type

        Returns:
            List[str]: Suggested capabilities
        """
        return self.capability_mapper.suggest_capabilities(text, intent_type)

    def _extract_features(self, text: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Extract features from text for classification

        Args:
            text: Text to analyze

        Returns:
            Dict[str, Any]: Extracted features  # TODO(TYPE): replace Any with concrete type
        """
        text_lower = text.lower().strip()

        features: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "text_length": len(text),
            "word_count": len(text.split()),
            "has_question": "?" in text,
            "has_exclamation": "!" in text,
            "entities": self._extract_entities(text),
            "keywords": [],
            "patterns": [],
        }

        # Extract keywords from all intent classifiers
        all_keywords: set[str] = set()
        for classifier_config in self.intent_classifiers.values():
            all_keywords.update(classifier_config["keywords"])

        # Check for keyword presence
        for keyword in all_keywords:
            if keyword in text_lower:
                features["keywords"].append(keyword)

        # Check for pattern matches
        for intent_type, classifier_config in self.intent_classifiers.items():
            for pattern in classifier_config["patterns"]:
                if re.search(pattern, text_lower):
                    features["patterns"].append(f"{intent_type}:{pattern}")

        return features

    def _extract_entities(self, text: str) -> list[tuple[str, str]]:
        """
        Extract entities from text using simple pattern matching

        Args:
            text: Text to analyze

        Returns:
            List[Tuple[str, str]]: List[Any] of (entity_text, entity_type) tuples  # TODO(TYPE): replace Any with concrete type
        """
        entities: list[tuple[str, str]] = []
        # Simple entity patterns
        entity_patterns = {
            "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "URL": r"https?://[^\s]+",
            "FILE": r"\b\w+\.\w{2,4}\b",
            "NUMBER": r"\b\d+\.?\d*\b",
            "DATE": r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
        }

        for entity_type, pattern in entity_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append((match.group(), entity_type))

        return entities

    def _calculate_intent_score(
        self, features: dict[str, Any], classifier_config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """
        Calculate intent score based on features and classifier configuration

        Args:
            features: Extracted features
            classifier_config: Intent classifier configuration

        Returns:
            float: Intent score
        """
        score = 0.0

        # Keyword matching score
        keyword_matches = 0
        for keyword in classifier_config["keywords"]:
            if keyword in features["keywords"]:
                keyword_matches += 1

        if classifier_config["keywords"]:
            keyword_score = (keyword_matches / len(classifier_config["keywords"])) * 10
            score += keyword_score * self.feature_weights["keyword_match"]

        # Pattern matching score
        pattern_matches = 0
        for pattern_match in features["patterns"]:
            if pattern_match.startswith(f"{classifier_config}:"):
                pattern_matches += 1

        if classifier_config["patterns"]:
            pattern_score = min(pattern_matches / len(classifier_config["patterns"]) * 10, 10)
            score += pattern_score * self.feature_weights["pattern_match"]

        # Entity presence score
        relevant_entities = 0
        for entity_text, entity_type in features["entities"]:
            if entity_type in classifier_config["entities"]:
                relevant_entities += 1

        if classifier_config["entities"]:
            entity_score = min(relevant_entities / len(classifier_config["entities"]) * 10, 10)
            score += entity_score * self.feature_weights["entity_presence"]

        # Length factor (prefer reasonable length texts)
        text_length = features["text_length"]
        if 10 <= text_length <= 200:
            length_score = 5.0
        elif text_length < 10:
            length_score = 2.0
        else:
            length_score = max(3.0 - (text_length - 200) / 100, 1.0)

        score += length_score * self.feature_weights["length_factor"]

        return score


class GoalKnowledgeBase:
    """
    Knowledge base for storing and learning from goal parsing patterns
    """

    def __init__(self, storage_path: str | None = None) -> None:
        """
        Initialize goal knowledge base

        Args:
            storage_path: Optional path for persistent storage
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.storage_path = storage_path or "goal_knowledge.json"

        # In-memory storage for goal patterns
        self.learned_patterns: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "successful_parses": [],
            "failed_parses": [],
            "intent_corrections": [],
            "capability_mappings": {},
        }

        # Load existing knowledge if available
        self._load_knowledge()

        logger.info("GoalKnowledgeBase initialized")

    def record_successful_parse(
        self,
        goal_text: str,
        intent_result: IntentClassificationResult,
        goal_intent: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Record a successful goal parse for learning

        Args:
            goal_text: Original goal text
            intent_result: Intent classification result
            goal_intent: Final parsed goal intent
        """
        try:
            record = {
                "goal_text": goal_text,
                "intent_type": intent_result.intent_type,
                "confidence": intent_result.confidence,
                "features": intent_result.features,
                "parsed_intent": goal_intent,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.learned_patterns["successful_parses"].append(record)

            # Limit storage size
            if len(self.learned_patterns["successful_parses"]) > 1000:
                self.learned_patterns["successful_parses"] = self.learned_patterns[
                    "successful_parses"
                ][-1000:]

            self._save_knowledge()
            self.logger.debug(f"Recorded successful parse for: {goal_text[:50]}...")

        except Exception as e:
            self.logger.error(f"Failed to record successful parse: {e}")

    def record_failed_parse(self, goal_text: str, error: str) -> None:
        """
        Record a failed goal parse for analysis

        Args:
            goal_text: Goal text that failed to parse
            error: Error message or reason for failure
        """
        try:
            record = {
                "goal_text": goal_text,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.learned_patterns["failed_parses"].append(record)

            # Limit storage size
            if len(self.learned_patterns["failed_parses"]) > 500:
                self.learned_patterns["failed_parses"] = self.learned_patterns["failed_parses"][
                    -500:
                ]

            self._save_knowledge()
            self.logger.debug(f"Recorded failed parse for: {goal_text[:50]}...")

        except Exception as e:
            self.logger.error(f"Failed to record failed parse: {e}")

    def suggest_intent_improvements(self, goal_text: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Suggest intent improvements based on learned patterns

        Args:
            goal_text: Goal text to analyze

        Returns:
            List[Dict[str, Any]]: Suggested improvements  # TODO(TYPE): replace Any with concrete type
        """
        suggestions: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        try:
            goal_lower = goal_text.lower()

            # Find similar successful parses
            for record in self.learned_patterns["successful_parses"][-100:]:  # Check recent records
                recorded_text = record["goal_text"].lower()

                # Simple similarity check (can be enhanced)
                common_words = set(goal_lower.split()) & set(recorded_text.split())
                if len(common_words) >= 2:
                    suggestions.append(
                        {
                            "type": "similar_pattern",
                            "suggestion": f"Consider intent type: {record['intent_type']}",
                            "confidence": record["confidence"],
                            "similar_text": record["goal_text"][:100],
                        }
                    )

            # Check for patterns in failed parses
            for record in self.learned_patterns["failed_parses"][-50:]:
                recorded_text = record["goal_text"].lower()
                if goal_lower == recorded_text:
                    suggestions.append(
                        {
                            "type": "known_failure",
                            "suggestion": f"This pattern previously failed: {record['error']}",
                            "error": record["error"],
                        }
                    )

        except Exception as e:
            self.logger.error(f"Failed to generate suggestions: {e}")

        return suggestions

    def get_knowledge_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get statistics about the knowledge base

        Returns:
            Dict[str, Any]: Knowledge base statistics  # TODO(TYPE): replace Any with concrete type
        """
        return {
            "successful_parses": len(self.learned_patterns["successful_parses"]),
            "failed_parses": len(self.learned_patterns["failed_parses"]),
            "intent_corrections": len(self.learned_patterns["intent_corrections"]),
            "capability_mappings": len(self.learned_patterns["capability_mappings"]),
            "storage_path": self.storage_path,
        }

    def _load_knowledge(self) -> None:
        """Load knowledge from persistent storage"""
        try:
            if Path(self.storage_path).exists():
                with open(self.storage_path, encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    self.learned_patterns.update(loaded_data)
                    self.logger.info(f"Loaded knowledge from {self.storage_path}")
        except Exception as e:
            self.logger.warning(f"Could not load knowledge: {e}")

    def _save_knowledge(self) -> None:
        """Save knowledge to persistent storage"""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.learned_patterns, f, indent=2, ensure_ascii=True)
        except Exception as e:
            self.logger.error(f"Failed to save knowledge: {e}")


def create_intent_classifier() -> LightweightIntentClassifier:
    """
    Create and return a lightweight intent classifier instance

    Returns:
        LightweightIntentClassifier: Configured classifier
    """
    return LightweightIntentClassifier()


def create_goal_knowledge_base(storage_path: str | None = None) -> GoalKnowledgeBase:
    """
    Create and return a goal knowledge base instance

    Args:
        storage_path: Optional path for persistent storage

    Returns:
        GoalKnowledgeBase: Configured knowledge base
    """
    return GoalKnowledgeBase(storage_path)


__all__ = [
    "IntentClassificationResult",
    "CapabilityMapper",
    "LightweightIntentClassifier",
    "GoalKnowledgeBase",
    "create_intent_classifier",
    "create_goal_knowledge_base",
]
