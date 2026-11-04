"""
Ethics Gate - Ethical Decision Making Framework
Provides ethical evaluation and validation for LLM decisions and actions
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EthicsLevel(Enum):
    """Ethics evaluation levels"""

    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    BLOCKED = "blocked"


class EthicsCategory(Enum):
    """Categories of ethical considerations"""

    PRIVACY = "privacy"
    SAFETY = "safety"
    FAIRNESS = "fairness"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    HARM_PREVENTION = "harm_prevention"


@dataclass
class EthicsEvaluation:
    """Ethics evaluation result"""

    level: EthicsLevel
    score: float  # 0-100, higher is more ethical
    concerns: list[str]
    recommendations: list[str]
    category_scores: dict[EthicsCategory, float]
    timestamp: datetime


@dataclass
class EthicsAssessment:
    """Ethics assessment for compatibility with phase2_endpoints"""

    passed: bool
    score: float
    concerns: list[str]
    level: str


class EthicsGate:
    """Ethical evaluation system for AI decisions"""

    def __init__(self) -> None:
        self.evaluations: list[EthicsEvaluation] = []
        self.blocked_patterns: list[str] = []
        self.warning_patterns: list[str] = []

        # Initialize with basic ethical patterns
        self._initialize_patterns()

        logger.info("Ethics Gate initialized")

    def _initialize_patterns(self) -> None:
        """Initialize basic ethical patterns"""
        self.blocked_patterns = [
            "harmful content",
            "privacy violation",
            "discriminatory",
            "malicious intent",
        ]

        self.warning_patterns = [
            "sensitive data",
            "personal information",
            "financial data",
            "medical information",
        ]

    async def evaluate(self, content: str, context: dict[str, Any]) -> EthicsEvaluation:  # TODO(TYPE): replace Any with concrete type
        """
        Evaluate content for ethical concerns

        Args:
            content: Content to evaluate
            context: Context information

        Returns:
            EthicsEvaluation with assessment results
        """
        # Perform ethical analysis
        level, score, concerns, recommendations = self._analyze_content(content, context)

        # Calculate category scores
        category_scores = self._calculate_category_scores(content, context)

        evaluation = EthicsEvaluation(
            level=level,
            score=score,
            concerns=concerns,
            recommendations=recommendations,
            category_scores=category_scores,
            timestamp=datetime.now(timezone.utc),
        )

        self.evaluations.append(evaluation)

        if level == EthicsLevel.BLOCKED:
            logger.warning(f"Ethics Gate BLOCKED content: {concerns}")
        elif level == EthicsLevel.WARNING:
            logger.info(f"Ethics Gate WARNING for content: {concerns}")

        return evaluation

    def _analyze_content(
        self, content: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[EthicsLevel, float, list[str], list[str]]:
        """Analyze content for ethical issues"""
        concerns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        score = 100.0

        content_lower = content.lower()

        # Check blocked patterns
        for pattern in self.blocked_patterns:
            if pattern in content_lower:
                concerns.append(f"Blocked pattern detected: {pattern}")
                score -= 50

        # Check warning patterns
        for pattern in self.warning_patterns:
            if pattern in content_lower:
                concerns.append(f"Warning pattern detected: {pattern}")
                score -= 20

        # Determine level based on score
        if score < 30:
            level = EthicsLevel.BLOCKED
            recommendations.append("Content should be rejected")
        elif score < 60:
            level = EthicsLevel.WARNING
            recommendations.append("Review content before proceeding")
        elif score < 80:
            level = EthicsLevel.CAUTION
            recommendations.append("Monitor for ethical compliance")
        else:
            level = EthicsLevel.SAFE
            recommendations.append("Content appears ethically sound")

        return level, max(0, score), concerns, recommendations

    def _calculate_category_scores(
        self, content: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[EthicsCategory, float]:
        """Calculate scores for each ethics category"""
        scores: dict[EthicsCategory, float] = {}
        for category in EthicsCategory:
            # Basic scoring logic - can be enhanced
            scores[category] = 85.0  # Default good score

            if category == EthicsCategory.PRIVACY:
                if any(term in content.lower() for term in ["personal", "private", "confidential"]):
                    scores[category] = 60.0
            elif category == EthicsCategory.SAFETY:
                if any(term in content.lower() for term in ["harm", "danger", "risk"]):
                    scores[category] = 50.0
            elif category == EthicsCategory.FAIRNESS:
                if any(term in content.lower() for term in ["bias", "discriminat", "unfair"]):
                    scores[category] = 40.0

        return scores

    def is_blocked(self, evaluation: EthicsEvaluation) -> bool:
        """Check if content should be blocked"""
        return evaluation.level == EthicsLevel.BLOCKED

    def requires_review(self, evaluation: EthicsEvaluation) -> bool:
        """Check if content requires human review"""
        return evaluation.level in [EthicsLevel.WARNING, EthicsLevel.BLOCKED]

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get ethics gate metrics"""
        if not self.evaluations:
            return {
                "total_evaluations": 0,
                "level_distribution": {},
                "average_score": 0,
                "blocked_count": 0,
                "warning_count": 0,
            }

        level_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for level in EthicsLevel:
            level_counts[level.value] = sum(1 for eval in self.evaluations if eval.level == level)

        avg_score = sum(eval.score for eval in self.evaluations) / len(self.evaluations)

        return {
            "total_evaluations": len(self.evaluations),
            "level_distribution": level_counts,
            "average_score": round(avg_score, 2),
            "blocked_count": level_counts.get("blocked", 0),
            "warning_count": level_counts.get("warning", 0),
            "latest_evaluation": (
                self.evaluations[-1].timestamp.isoformat() if self.evaluations else None
            ),
        }

    def add_pattern(self, pattern: str, level: str) -> None:
        """Add new ethical pattern"""
        if level == "blocked":
            self.blocked_patterns.append(pattern)
        elif level == "warning":
            self.warning_patterns.append(pattern)

        logger.info(f"Added {level} pattern: {pattern}")

    def clear_evaluations(self) -> None:
        """Clear evaluation history"""
        cleared_count = len(self.evaluations)
        self.evaluations.clear()
        logger.info(f"Cleared {cleared_count} ethics evaluations")


# Global ethics gate instance
_global_gate: EthicsGate | None = None


def get_ethics_gate() -> EthicsGate:
    """Get global ethics gate instance"""
    global _global_gate
    if _global_gate is None:
        _global_gate = EthicsGate()
    return _global_gate


async def evaluate_ethics(
    content: str, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
) -> EthicsEvaluation:
    """Convenience function for ethics evaluation"""
    gate = get_ethics_gate()
    return await gate.evaluate(content, context or {})


def is_content_safe(content: str, context: dict[str, Any] | None = None) -> bool:  # TODO(TYPE): replace Any with concrete type
    """Quick check if content is ethically safe"""
    import asyncio

    loop = asyncio.get_event_loop()
    evaluation = loop.run_until_complete(evaluate_ethics(content, context))
    return evaluation.level in [EthicsLevel.SAFE, EthicsLevel.CAUTION]


# Compatibility exports for phase2_endpoints
def check_ethical_compliance(content: str) -> bool:
    """Check if content meets ethical standards"""
    return is_content_safe(content)


def get_ethics_metrics() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get ethics system metrics"""
    gate = get_ethics_gate()
    return gate.get_metrics()
