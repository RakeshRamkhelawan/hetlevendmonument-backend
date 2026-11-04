"""
Basic Ethics Gate for CVA Agent
Provides ethical guidelines and safety checks for AI decision-making
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EthicsLevel(Enum):
    """Ethics assessment levels"""

    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    BLOCKED = "blocked"


class EthicsCategory(Enum):
    """Categories of ethical concerns"""

    PRIVACY = "privacy"
    SAFETY = "safety"
    FAIRNESS = "fairness"
    TRANSPARENCY = "transparency"
    AUTONOMY = "autonomy"
    HARM_PREVENTION = "harm_prevention"
    BIAS = "bias"
    SECURITY = "security"


@dataclass
class EthicsAssessment:
    """Result of ethics assessment"""

    level: EthicsLevel
    score: float  # 0.0 = completely blocked, 1.0 = completely safe
    concerns: list[tuple[EthicsCategory, str]]  # (category, description)
    recommendations: list[str]
    requires_human_review: bool
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class BasicEthicsGate:
    """Basic ethics gate for Week 1 implementation"""

    def __init__(self) -> None:
        self.blocked_patterns = self._initialize_blocked_patterns()
        self.caution_patterns = self._initialize_caution_patterns()
        self.ethical_guidelines = self._initialize_guidelines()

        # Metrics
        self._assessments_count = 0
        self._blocked_count = 0
        self._warning_count = 0

        logger.info("Basic Ethics Gate initialized")

    def _initialize_blocked_patterns(self) -> list[str]:
        """Initialize patterns that should be completely blocked"""
        return [
            r"\b(harm|hurt|damage|attack|destroy|illegal|malicious)\b",
            r"\b(personal\s+information|private\s+data|confidential)\b",
            r"\b(bypass|circumvent|hack|exploit|vulnerability)\b",
            r"\b(discriminat|bias|unfair|prejudice)\s+against",
            r"\b(violat|breach|break)\s+(law|regulation|policy)",
        ]

    def _initialize_caution_patterns(self) -> list[str]:
        """Initialize patterns that require caution"""
        return [
            r"\b(decision|choose|select|recommend)\s+(for|about)\s+(user|person|people)",
            r"\b(collect|gather|store|process)\s+(data|information)",
        ]

    def _initialize_guidelines(self) -> dict[str, list[str]]:
        """Initialize ethical guidelines by category"""
        return {
            "privacy": [
                "Minimize personal data collection",
                "Ensure explicit consent for data use",
                "Provide clear data handling transparency",
                "Implement data minimization principles",
            ],
            "safety": [
                "Avoid recommendations that could cause harm",
                "Include safety warnings for risky activities",
                "Provide emergency contact information when appropriate",
                "Test thoroughly before deployment",
            ],
            "fairness": [
                "Ensure equal treatment across user groups",
                "Avoid biased language or recommendations",
                "Consider diverse perspectives in decision-making",
                "Monitor for discriminatory outcomes",
            ],
            "transparency": [
                "Clearly identify AI-generated content",
                "Explain reasoning behind decisions",
                "Provide information about limitations",
                "Enable user understanding of AI behavior",
            ],
            "autonomy": [
                "Preserve human decision-making authority",
                "Provide options rather than single recommendations",
                "Enable user control over AI behavior",
                "Respect user preferences and choices",
            ],
        }

    def _is_strategic_document(self, text: str) -> bool:
        """Detect if this is a strategic document for CVA analysis"""
        strategic_indicators = [
            "strategie",
            "strategic",
            "document",
            "manifest",
            "plan",
            "roadmap",
            "architectur",
            "vision",
            "policy",
            "framework",
            "governance",
            "bewustzijn",
            "consciousness",
            "ai systeem",
            "ontwikkeling",
        ]

        text_lower = text.lower()

        # Check for multiple strategic indicators
        matches = sum(1 for indicator in strategic_indicators if indicator in text_lower)

        # Also check for formal document structure
        has_structure = any(
            marker in text_lower
            for marker in [
                "hoofdstuk",
                "chapter",
                "##",
                "###",
                "versie",
                "version",
                "inhoudsopgave",
                "table of contents",
                "samenvatting",
                "summary",
            ]
        )

        # If it has many strategic terms AND document structure, it's likely a strategic doc
        return matches >= 3 and has_structure

    async def assess_task(
        self, task_description: str, metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> EthicsAssessment:
        """Assess a task for ethical concerns"""
        self._assessments_count += 1

        # Initialize assessment
        concerns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        score = 1.0
        level = EthicsLevel.SAFE
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        blocked_matches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        caution_matches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        category_concerns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Special handling for strategic documents
        if self._is_strategic_document(task_description):
            # Allow strategic documents for CVA analysis with minimal restrictions
            return EthicsAssessment(
                level=EthicsLevel.SAFE,
                score=0.9,  # High but not perfect due to complexity
                concerns=[
                    (
                        EthicsCategory.TRANSPARENCY,
                        "Strategic document analysis - requires thorough CVA review",
                    )
                ],
                recommendations=[
                    "Provide comprehensive strategic analysis",
                    "Consider long-term implications",
                ],
                requires_human_review=False,
                metadata={
                    "assessment_id": f"ethics_strategic_{self._assessments_count}",
                    "document_type": "strategic_document",
                    "handling": "cva_analysis_mode",
                },
            )

        # Check for blocked content
        blocked_matches = self._check_patterns(task_description, self.blocked_patterns)
        if blocked_matches:
            concerns.append(
                (
                    EthicsCategory.HARM_PREVENTION,
                    f"Blocked content detected: {', '.join(blocked_matches)}",
                )
            )
            score = 0.0
            level = EthicsLevel.BLOCKED
            self._blocked_count += 1
            recommendations.append(
                "This task contains content that violates ethical guidelines and cannot be processed"
            )

        # Check for caution content (if not already blocked)
        if level != EthicsLevel.BLOCKED:
            caution_matches = self._check_patterns(task_description, self.caution_patterns)
            if caution_matches:
                concerns.append(
                    (
                        EthicsCategory.SAFETY,
                        f"Caution required: {', '.join(caution_matches)}",
                    )
                )
                score = max(0.3, score - 0.4)
                level = EthicsLevel.WARNING if score < 0.5 else EthicsLevel.CAUTION
                self._warning_count += 1
                recommendations.extend(
                    [
                        "Review human oversight requirements",
                        "Consider additional safety measures",
                        "Ensure clear user communication about AI involvement",
                    ]
                )

        # Check specific ethical categories
        category_concerns = self._assess_categories(task_description, metadata)
        concerns.extend(category_concerns)

        # Adjust score based on category concerns
        if category_concerns:
            score = max(0.1, score - (len(category_concerns) * 0.1))
            if score < 0.3:
                level = EthicsLevel.BLOCKED
            elif score < 0.6:
                level = EthicsLevel.WARNING
            elif score < 0.8:
                level = EthicsLevel.CAUTION

        # Determine if human review is required
        requires_human_review = (
            level in [EthicsLevel.BLOCKED, EthicsLevel.WARNING]
            or metadata.get("risk_level", 0) >= 7
            or any(cat in [EthicsCategory.PRIVACY, EthicsCategory.SAFETY] for cat, _ in concerns)
        )

        # Add general recommendations if no specific ones
        if not recommendations and concerns:
            recommendations = self._get_general_recommendations(concerns)

        return EthicsAssessment(
            level=level,
            score=score,
            concerns=concerns,
            recommendations=recommendations,
            requires_human_review=requires_human_review,
            metadata={
                "assessment_id": f"ethics_{self._assessments_count}",
                "patterns_matched": len(blocked_matches) + len(caution_matches),
                "category_concerns": len(category_concerns),
            },
        )

    async def assess_response(self, response_content: str, original_task: str) -> EthicsAssessment:
        """Assess an AI response before delivery"""
        # For Week 1, we'll do basic response checking
        # In Week 2+, this could be enhanced with more sophisticated analysis

        response_metadata = {
            "type": "response_assessment",
            "original_task": (
                original_task[:100] + "..." if len(original_task) > 100 else original_task
            ),
        }

        return await self.assess_task(response_content, response_metadata)

    def _check_patterns(self, text: str, patterns: list[str]) -> list[str]:
        """Check text against a list of regex patterns"""
        matches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        text_lower = text.lower()

        for pattern in patterns:
            if re.search(pattern, text_lower):
                # Extract the matched portion for reporting
                match = re.search(pattern, text_lower)
                if match:
                    matches.append(match.group())

        return matches

    def _assess_categories(
        self, text: str, metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[tuple[EthicsCategory, str]]:
        """Assess specific ethical categories"""
        concerns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        text_lower = text.lower()

        # Skip detailed category analysis for strategic documents
        if self._is_strategic_document(text):
            return []  # Strategic documents get special handling

        # Privacy concerns - only for actual personal data handling
        if any(
            phrase in text_lower
            for phrase in [
                "collect personal data",
                "store user information",
                "share private data",
            ]
        ):
            concerns.append((EthicsCategory.PRIVACY, "Task involves active personal data handling"))

        # Safety concerns - only for actual risky actions
        if any(
            phrase in text_lower
            for phrase in ["perform dangerous", "risky action", "unsafe operation"]
        ):
            concerns.append((EthicsCategory.SAFETY, "Task involves potentially dangerous actions"))

        # Autonomy concerns - only for decisions that bypass users
        if any(
            phrase in text_lower
            for phrase in [
                "decide for user",
                "automatic action without consent",
                "override user choice",
            ]
        ):
            concerns.append((EthicsCategory.AUTONOMY, "Task may bypass user decision-making"))

        # Fairness/Bias concerns - only for discriminatory actions
        if any(
            phrase in text_lower
            for phrase in ["discriminate against", "exclude based on", "bias towards"]
        ):
            concerns.append((EthicsCategory.FAIRNESS, "Task may involve discriminatory actions"))

        # Check metadata for additional concerns
        risk_level = metadata.get("risk_level", 0)
        if risk_level >= 9:  # Only very high risk levels
            concerns.append(
                (
                    EthicsCategory.HARM_PREVENTION,
                    f"Very high risk level ({risk_level}) requires careful review",
                )
            )

        return concerns

    def _get_general_recommendations(self, concerns: list[tuple[EthicsCategory, str]]) -> list[str]:
        """Get general recommendations based on concern categories"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        categories = [cat for cat, _ in concerns]

        if EthicsCategory.PRIVACY in categories:
            recommendations.extend(
                [
                    "Implement privacy-preserving techniques",
                    "Minimize data collection to essential needs",
                    "Ensure clear consent mechanisms",
                ]
            )

        if EthicsCategory.SAFETY in categories:
            recommendations.extend(
                [
                    "Add safety warnings and disclaimers",
                    "Implement additional validation checks",
                    "Provide alternative safer options",
                ]
            )

        if EthicsCategory.AUTONOMY in categories:
            recommendations.extend(
                [
                    "Preserve user choice and control",
                    "Provide multiple options instead of single recommendations",
                    "Enable user override of AI decisions",
                ]
            )

        if EthicsCategory.FAIRNESS in categories:
            recommendations.extend(
                [
                    "Review for potential bias in recommendations",
                    "Ensure equal treatment across user groups",
                    "Test with diverse user scenarios",
                ]
            )

        return list(set(recommendations))  # Remove duplicates

    def get_guidelines(self, category: str | None = None) -> dict[str, list[str]]:
        """Get ethical guidelines for a specific category or all categories"""
        if category:
            return {category: self.ethical_guidelines.get(category, [])}
        return self.ethical_guidelines

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get ethics gate metrics"""
        return {
            "total_assessments": self._assessments_count,
            "blocked_count": self._blocked_count,
            "warning_count": self._warning_count,
            "block_rate": self._blocked_count / max(self._assessments_count, 1),
            "warning_rate": self._warning_count / max(self._assessments_count, 1),
            "guidelines_categories": len(self.ethical_guidelines),
        }

    def is_task_allowed(self, assessment: EthicsAssessment) -> bool:
        """Check if a task is allowed based on assessment"""
        return assessment.level != EthicsLevel.BLOCKED

    def requires_approval(self, assessment: EthicsAssessment) -> bool:
        """Check if a task requires human approval"""
        return assessment.requires_human_review or assessment.level in [
            EthicsLevel.BLOCKED,
            EthicsLevel.WARNING,
        ]


# Global ethics gate instance
_ethics_gate = BasicEthicsGate()


def get_ethics_gate() -> BasicEthicsGate:
    """Get the global ethics gate instance"""
    return _ethics_gate
