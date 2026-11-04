"""
Machine Learning for automatic rule generation.

Provides:
- Automatic rule generation from insights
- Confidence score prediction
- Pattern detection in feedback
"""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.learning.loop import AdaptationRule, LearningInsight

logger = logging.getLogger(__name__)


@dataclass
class RuleSuggestion:
    """Suggested rule from ML analysis."""

    trigger_keywords: list[str]
    target_supervisor: str
    confidence: float
    reasoning: str
    source_insights: list[str]


class SimpleRuleGenerator:
    """
    Simple rule generator based on pattern analysis.

    This is a lightweight implementation that doesn't require
    external ML libraries. For production, consider using:
    - scikit-learn for clustering
    - transformers for NLP
    """

    def __init__(self) -> None:
        self.min_confidence = 0.7
        self.min_occurrences = 3

    def analyze_insights(self, insights: list[LearningInsight]) -> list[RuleSuggestion]:
        """
        Analyze insights and suggest new rules.

        Args:
            insights: List[Any] of learning insights to analyze  # TODO(TYPE): replace Any with concrete type

        Returns: List[Any] of suggested rules  # TODO(TYPE): replace Any with concrete type
        """
        if len(insights) < self.min_occurrences:
            logger.info(f"Not enough insights for analysis: {len(insights)}")
            return []

        suggestions: list[RuleSuggestion] = []

        # Group insights by category
        routing_errors = [
            i for i in insights if i.category == "routing_error" and not i.adaptation_applied
        ]

        if routing_errors:
            # Analyze routing errors for patterns
            routing_suggestions = self._analyze_routing_errors(routing_errors)
            suggestions.extend(routing_suggestions)

        # Analyze keyword patterns
        keyword_suggestions = self._analyze_keyword_patterns(insights)
        suggestions.extend(keyword_suggestions)

        return suggestions

    def _analyze_routing_errors(self, errors: list[LearningInsight]) -> list[RuleSuggestion]:
        """Analyze routing errors for patterns."""
        suggestions: list[RuleSuggestion] = []

        # Group by target supervisor
        by_target: dict[str, list[LearningInsight]] = {}
        for error in errors:
            context = error.context or {}
            target = context.get("should_have_routed_to")
            if target:
                if target not in by_target:
                    by_target[target] = []
                by_target[target].append(error)

        # Find patterns per target
        for target, target_errors in by_target.items():
            if len(target_errors) < self.min_occurrences:
                continue

            # Extract common keywords
            all_keywords: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for error in target_errors:
                query = (error.context or {}).get("query", "")
                keywords = self._extract_keywords(query)
                all_keywords.extend(keywords)

            # Find frequent keywords
            keyword_counts = Counter(all_keywords)
            common_keywords = [
                kw for kw, count in keyword_counts.items() if count >= self.min_occurrences
            ]

            if common_keywords:
                confidence = min(0.95, 0.7 + (len(target_errors) * 0.05))
                suggestions.append(
                    RuleSuggestion(
                        trigger_keywords=common_keywords[:5],  # Top 5 keywords
                        target_supervisor=target,
                        confidence=confidence,
                        reasoning=f"Based on {len(target_errors)} similar routing errors",
                        source_insights=[e.id for e in target_errors],
                    )
                )

        return suggestions

    def _analyze_keyword_patterns(self, insights: list[LearningInsight]) -> list[RuleSuggestion]:
        """Analyze general keyword patterns in insights."""
        suggestions: list[RuleSuggestion] = []

        # Extract all queries
        queries: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for insight in insights:
            context = insight.context or {}
            query = context.get("query", "")
            if query:
                queries.append(query.lower())

        if not queries:
            return suggestions

        # Find common word pairs (bigrams)
        bigrams: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for query in queries:
            words = query.split()
            for i in range(len(words) - 1):
                bigrams.append(f"{words[i]} {words[i + 1]}")

        bigram_counts = Counter(bigrams)
        common_bigrams = [
            bg for bg, count in bigram_counts.items() if count >= self.min_occurrences
        ]

        # This is a simplified version
        # In production, you'd use more sophisticated NLP

        return suggestions

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract relevant keywords from a query."""
        # Common stop words to exclude
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "need",
            "please",
            "help",
            "me",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "my",
            "your",
            "his",
            "her",
            "its",
            "our",
            "their",
            "this",
            "that",
            "these",
            "those",
        }

        words = query.lower().split()
        keywords = [
            w.strip(".,!?;:") for w in words if w.strip(".,!?;:") not in stop_words and len(w) > 2
        ]

        return keywords

    def predict_rule_confidence(
        self, trigger_keywords: list[str], historical_rules: list[AdaptationRule]
    ) -> float:
        """
        Predict confidence score for a new rule.

        This is a simple heuristic-based prediction.
        For production, train a ML model on historical data.
        """
        if not historical_rules:
            return 0.75  # Default confidence

        # Find similar historical rules
        similar_rules: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for rule in historical_rules:
            rule_keywords = rule.trigger_keywords or []
            overlap = set(trigger_keywords) & set(rule_keywords)
            if overlap:
                similar_rules.append(rule)

        if not similar_rules:
            return 0.75

        # Average success rate of similar rules
        avg_success: float = sum(float(r.success_rate) for r in similar_rules) / len(similar_rules)

        # Adjust based on number of similar rules
        confidence: float = avg_success * (0.8 + 0.2 * min(len(similar_rules) / 5, 1))

        return min(confidence, 0.95)


class PatternDetector:
    """
    Detect patterns in feedback and insights.
    """

    def __init__(self) -> None:
        self.min_pattern_length = 2

    def detect_patterns(self, insights: list[LearningInsight]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Detect patterns in insights.

        Returns: List[Any] of detected patterns  # TODO(TYPE): replace Any with concrete type
        """
        patterns: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        # Detect time-based patterns
        time_patterns = self._detect_time_patterns(insights)
        patterns.extend(time_patterns)

        # Detect category patterns
        category_patterns = self._detect_category_patterns(insights)
        patterns.extend(category_patterns)

        return patterns

    def _detect_time_patterns(self, insights: list[LearningInsight]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Detect time-based patterns."""
        from datetime import datetime

        if not insights:
            return []

        # Group by hour of day
        hour_counts: Counter[int] = Counter()
        for insight in insights:
            if insight.created_at:
                hour = insight.created_at.hour
                hour_counts[hour] += 1

        # Find peak hours
        max_count = max(hour_counts.values()) if hour_counts else 0
        peak_hours = [h for h, count in hour_counts.items() if count > max_count * 0.7]

        if peak_hours:
            return [
                {
                    "type": "time_pattern",
                    "description": f"Peak activity at hours: {peak_hours}",
                    "confidence": 0.8,
                    "details": {"peak_hours": peak_hours},
                }
            ]

        return []

    def _detect_category_patterns(self, insights: list[LearningInsight]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Detect category-based patterns."""
        categories = Counter(i.category for i in insights if i.category)

        patterns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        total = len(insights)

        for category, count in categories.most_common(3):
            percentage = count / total if total > 0 else 0
            if percentage > 0.2:  # More than 20%
                patterns.append(
                    {
                        "type": "category_pattern",
                        "description": f"High occurrence of {category}: {percentage:.1%}",
                        "confidence": min(percentage + 0.5, 0.95),
                        "details": {"category": category, "count": count},
                    }
                )

        return patterns


# Convenience function for generating rules
async def generate_rules_from_insights(insights: list[LearningInsight]) -> list[AdaptationRule]:
    """
    Generate adaptation rules from insights using ML.

    Usage:
        new_rules = await generate_rules_from_insights(insights)
        for rule in new_rules:
            await save_rule(rule)
    """
    import uuid

    generator = SimpleRuleGenerator()
    suggestions = generator.analyze_insights(insights)

    rules: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for suggestion in suggestions:
        if suggestion.confidence >= 0.7:
            rule = AdaptationRule(
                id=f"rule_ml_{uuid.uuid4().hex[:8]}",
                rule_type="routing_correction",
                trigger_keywords=suggestion.trigger_keywords,
                target_supervisor=suggestion.target_supervisor,
                confidence=suggestion.confidence,
                priority=int(suggestion.confidence * 10),
                active=True,
            )
            rules.append(rule)

    return rules
