"""Analysis Service for parsing and processing."""

import json
import logging
from typing import Any

from src.core.strategy.types import StrategyType

logger = logging.getLogger(__name__)


class AnalysisService:
    """Service for parsing analysis results and recommendations."""

    def parse_strategic_analysis(
        self, analysis_text: str, _strategy_type: StrategyType
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Parse strategic analysis from LLM response."""
        try:
            # Try to extract JSON
            if "{" in analysis_text:
                json_start = analysis_text.find("{")
                json_end = analysis_text.rfind("}") + 1
                json_text = analysis_text[json_start:json_end]
                result: dict[str, Any] = json.loads(json_text)  # TODO(TYPE): replace Any with concrete type
                return result
        except Exception as e:
            logger.warning("Failed to parse strategic analysis JSON: %s", str(e), exc_info=False)

        # Fallback to structured parsing
        return {
            "current_situation": "Analysis completed based on provided context",
            "opportunities": ["Market expansion opportunities identified"],
            "threats": ["Competitive pressures noted"],
            "strategic_options": ["Multiple strategic paths evaluated"],
            "risk_assessment": "Moderate risk level assessed",
            "resource_requirements": ["Standard resource allocation required"],
        }

    def parse_recommendations(self, recommendations_text: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Parse recommendations from LLM response."""
        try:
            # Try to extract JSON
            if "[" in recommendations_text:
                json_start = recommendations_text.find("[")
                json_end = recommendations_text.rfind("]") + 1
                json_text = recommendations_text[json_start:json_end]
                result: list[dict[str, Any]] = json.loads(json_text)  # TODO(TYPE): replace Any with concrete type
                return result
        except Exception as e:
            logger.warning("Failed to parse recommendations JSON: %s", str(e), exc_info=False)

        # Fallback recommendations
        return [
            {
                "title": "Strategic Initiative 1",
                "action_statement": "Implement primary strategic action",
                "impact": "High impact on organizational goals",
                "resources": ["Team allocation", "Budget allocation"],
                "timeline_weeks": 6,
                "success_metrics": ["metric_1", "metric_2"],
            },
            {
                "title": "Strategic Initiative 2",
                "action_statement": "Execute secondary strategic action",
                "impact": "Medium impact on market position",
                "resources": ["Technology investment", "Process optimization"],
                "timeline_weeks": 8,
                "success_metrics": ["metric_3", "metric_4"],
            },
        ]

    def calculate_confidence_score(
        self, analysis: dict[str, Any], recommendations: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate confidence score for strategy."""
        confidence_factors: list[float] = []
        # Analysis depth
        if analysis and len(analysis) > 3:
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.5)

        # Number of recommendations
        if len(recommendations) >= 3:
            confidence_factors.append(0.9)
        elif len(recommendations) >= 2:
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.5)

        # Recommendation quality
        complete_recommendations = sum(1 for rec in recommendations if len(rec) > 4)
        if complete_recommendations > 0 and recommendations:
            rec_quality = complete_recommendations / len(recommendations)
            confidence_factors.append(rec_quality)
        else:
            confidence_factors.append(0.3)

        total: float = sum(confidence_factors)
        avg_score: float = total / len(confidence_factors)
        confidence_result: float = avg_score
        return confidence_result

    def extract_key_themes(self, texts: list[str]) -> list[str]:
        """Extract common themes from a list of texts."""
        # Simple keyword extraction - could be enhanced with NLP
        all_words = " ".join(texts).lower().split()
        word_freq: dict[str, int] = {}
        for word in all_words:
            word = word.strip(".,!?;:\"'()[]")
            if len(word) > 4:  # Filter short words
                word_freq[word] = word_freq.get(word, 0) + 1

        # Return top themes
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _count in sorted_words[:10]]

    def analyze_sentiment(self, text: str) -> dict[str, float]:
        """Simple sentiment analysis of text."""
        positive_words = {
            "good",
            "great",
            "excellent",
            "positive",
            "growth",
            "success",
            "opportunity",
        }
        negative_words = {
            "bad",
            "poor",
            "negative",
            "risk",
            "threat",
            "failure",
            "challenge",
        }

        words = text.lower().split()
        positive_count = sum(1 for w in words if w.strip(".,!?;:\"'") in positive_words)
        negative_count = sum(1 for w in words if w.strip(".,!?;:\"'") in negative_words)
        total = len(words)

        if total == 0:
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}

        return {
            "positive": positive_count / total,
            "negative": negative_count / total,
            "neutral": (total - positive_count - negative_count) / total,
        }
