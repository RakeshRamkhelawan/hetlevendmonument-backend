"""
Media Vertical - Content Moderation & Bias Detection
Implements toxicity scoring and multi-dimensional bias detection.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class BiasType(Enum):
    """Types of bias detected in content"""

    GENDER = "gender"
    RACIAL = "racial"
    AGE = "age"
    CLASS = "class"
    GEOGRAPHIC = "geographic"


class ModerationAction(Enum):
    """Content moderation recommendations"""

    APPROVE = "approve"
    FLAG = "flag_for_review"
    REMOVE = "remove_content"


@dataclass
class ContentSubmission:
    """User-generated content for moderation"""

    content_id: str
    text: str
    author_id: str
    content_type: str  # "article", "comment", "image_caption"
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class MediaModerationAgent:
    """
    Content moderation expert with bias awareness.
    Detects toxicity, bias, and misinformation.
    """

    MODERATION_PROMPT = """
You are a content moderation expert with bias awareness.
Content: {text}
Task: Detect: toxicity, bias (gender/race/age/class/geo), misinformation.
Output: {{
  "toxicity_score": 0-1,
  "bias_types": ["gender", "racial"],
  "bias_explanation": "string",
  "recommendation": "approve|flag|remove",
  "reason": "detailed explanation for editor"
}}
Explain reasoning in plain English for editor override.

Bias Detection Rules:
1. Gender: Stereotypes, diminutives, gendered assumptions
2. Racial: Slurs, stereotypes, coded language
3. Age: Ageism, generational stereotypes
4. Class: Economic stereotypes, elitism
5. Geographic: Regional stereotypes, othering

Toxicity Thresholds:
- <0.3: Approve
- 0.3-0.7: Flag for review
- >0.7: Remove
"""

    def __init__(self, audit_service: Any | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        self.audit_service = audit_service
        self.bias_keywords = {
            BiasType.GENDER: ["bossy", "emotional", "hysterical", "shrill"],
            BiasType.RACIAL: ["exotic", "articulate", "urban", "thug"],
            BiasType.AGE: ["millennial", "boomer", "old-fashioned", "entitled"],
            BiasType.CLASS: ["lowlife", "elite", "trashy", "privileged"],
            BiasType.GEOGRAPHIC: ["backward", "provincial", "cosmopolitan", "flyover"],
        }

    def detect_bias(self, content: ContentSubmission) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Detect bias types in content using keyword heuristics.

        Args:
            content: Content submission to analyze

        Returns:
            Bias analysis with detected types and explanations
        """
        text_lower = content.text.lower()
        detected_biases: list[str] = []
        bias_explanations: list[str] = []

        for bias_type, keywords in self.bias_keywords.items():
            found_keywords = [kw for kw in keywords if kw in text_lower]
            if found_keywords:
                detected_biases.append(bias_type.value)
                bias_explanations.append(
                    f"{bias_type.value.title()} bias: Keywords '{', '.join(found_keywords)}' detected"
                )

        return {
            "content_id": content.content_id,
            "bias_types": detected_biases,
            "bias_explanation": (
                "; ".join(bias_explanations) if bias_explanations else "No bias detected"
            ),
        }

    def calculate_toxicity(self, content: ContentSubmission) -> float:
        """
        Calculate toxicity score using simple heuristics.
        In production, use Perspective API or similar ML model.

        Args:
            content: Content to analyze

        Returns:
            Toxicity score (0-1)
        """
        toxic_keywords = [
            "hate",
            "kill",
            "stupid",
            "idiot",
            "disgusting",
            "worthless",
            "pathetic",
            "loser",
            "trash",
        ]

        text_lower = content.text.lower()
        toxic_count = sum(1 for keyword in toxic_keywords if keyword in text_lower)

        # Simple scoring: 0.15 per toxic keyword, capped at 1.0
        toxicity_score = min(toxic_count * 0.15, 1.0)

        return toxicity_score

    async def moderate_content(self, content: ContentSubmission) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Full moderation analysis: toxicity + bias + recommendation.

        Args:
            content: Content submission to moderate

        Returns:
            Moderation result with recommendation and reasoning
        """
        toxicity_score = self.calculate_toxicity(content)
        bias_analysis = self.detect_bias(content)

        # Determine recommendation
        if toxicity_score > 0.7:
            recommendation = ModerationAction.REMOVE
            reason = f"High toxicity ({toxicity_score:.2f}): Content violates community standards"
        elif toxicity_score > 0.3 or bias_analysis["bias_types"]:
            recommendation = ModerationAction.FLAG
            reason = (
                f"Moderate toxicity ({toxicity_score:.2f}) or bias detected: Editor review required"
            )
        else:
            recommendation = ModerationAction.APPROVE
            reason = (
                f"Low toxicity ({toxicity_score:.2f}), no significant bias: Content meets standards"
            )

        result = {
            "content_id": content.content_id,
            "toxicity_score": toxicity_score,
            "bias_types": bias_analysis["bias_types"],
            "bias_explanation": bias_analysis["bias_explanation"],
            "recommendation": recommendation.value,
            "reason": reason,
            "requires_editor_review": recommendation == ModerationAction.FLAG,
        }

        # Log to audit trail
        if self.audit_service:
            await self.audit_service.log_action(
                tenant_id="media_tenant",
                action="CONTENT_MODERATION",
                resource=f"content:{content.content_id}",
                details={
                    "author_id": content.author_id,
                    "recommendation": recommendation.value,
                    "toxicity_score": toxicity_score,
                    "bias_types": bias_analysis["bias_types"],
                },
            )

        return result

    @staticmethod
    def get_prompt_template() -> str:
        """Return the LLM prompt template for moderation"""
        return MediaModerationAgent.MODERATION_PROMPT
