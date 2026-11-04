"""Attribution Labels for EU AI Act Article 53 compliance.

Task 10: Content Attribution Labels
Provides metadata labels for AI-generated content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class AttributionLabel:
    """Attribution label for AI-generated content.

    Per Article 53, users must be able to identify AI-generated content.
    """

    is_ai_generated: bool = True
    provider: str = ""
    model: str = ""
    model_version: str = ""
    generation_timestamp: datetime | None = None
    prompt_hash: str | None = None
    confidence_score: float | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for embedding in responses."""
        return {
            "ai_act_compliant": True,
            "is_ai_generated": self.is_ai_generated,
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "generated_at": (
                self.generation_timestamp.isoformat() if self.generation_timestamp else None
            ),
            "prompt_hash": self.prompt_hash,
            "confidence": self.confidence_score,
        }

    def to_html_comment(self) -> str:
        """Convert to HTML comment for web content."""
        return f"""<!--
AI-Generated Content Attribution (EU AI Act Article 53):
- Provider: {self.provider}
- Model: {self.model}
- Version: {self.model_version}
- Generated: {self.generation_timestamp.isoformat() if self.generation_timestamp else "Unknown"}
-->"""

    def to_text_footer(self) -> str:
        """Convert to text footer for documents."""
        lines = [
            "",
            "---",
            "AI-Generated Content Attribution (EU AI Act):",
            f"Provider: {self.provider}",
            f"Model: {self.model} ({self.model_version})",
        ]
        if self.generation_timestamp:
            lines.append(f"Generated: {self.generation_timestamp.isoformat()}")
        return "\n".join(lines)


def create_attribution_label(
    provider: str,
    model: str,
    model_version: str,
    prompt_hash: str | None = None,
    confidence: float | None = None,
) -> AttributionLabel:
    """Create an attribution label for AI-generated content.

    Args:
        provider: LLM provider
        model: Model name
        model_version: Model version
        prompt_hash: Hash of input prompt
        confidence: Confidence score

    Returns:
        Attribution label
    """
    return AttributionLabel(
        is_ai_generated=True,
        provider=provider,
        model=model,
        model_version=model_version,
        generation_timestamp=datetime.now(timezone.utc),
        prompt_hash=prompt_hash,
        confidence_score=confidence,
    )


def get_ai_disclosure_text(provider: str = "SanskritiSetu AI") -> str:
    """Return an EU AI Act Art. 52 disclosure message for use at interaction start.

    Must be shown to users before or at the start of any AI-mediated interaction
    so they understand they are communicating with an AI system.
    """
    return (
        f"You are interacting with an AI system provided by {provider}. "
        "This AI is designed to assist you with business process automation. "
        "Responses are generated automatically and may not always be accurate. "
        "EU AI Act Art. 52 disclosure: this system uses artificial intelligence."
    )


def add_attribution_to_response(
    response_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    provider: str,
    model: str,
    model_version: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Add attribution label to response data.

    Args:
        response_data: Original response
        provider: LLM provider
        model: Model name
        model_version: Model version

    Returns:
        Response with attribution added
    """
    label = create_attribution_label(provider, model, model_version)

    response_data["_ai_attribution"] = label.to_dict()
    return response_data
