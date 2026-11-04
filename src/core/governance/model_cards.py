"""Model Cards Registry for EU AI Act Article 53 compliance.

Task 8: Model Cards Registry
Tracks GPAI model metadata per Article 53 requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ModelCard:
    """Model Card per EU AI Act Article 53.

    Tracks technical documentation for GPAI models including
    capabilities, limitations, and systemic risk classification.
    """

    provider: str
    model_name: str
    model_id: str
    version: str = ""
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    training_data_summary: str = ""
    is_systemic_risk: bool = False
    flops_estimate: str | None = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "model_id": self.model_id,
            "version": self.version,
            "capabilities": self.capabilities,
            "limitations": self.limitations,
            "training_data_summary": self.training_data_summary,
            "is_systemic_risk": self.is_systemic_risk,
            "flops_estimate": self.flops_estimate,
            "registered_at": self.registered_at.isoformat(),
        }


# Registry of known GPAI models
MODEL_REGISTRY: dict[str, ModelCard] = {
    "gpt-4": ModelCard(
        provider="OpenAI",
        model_name="GPT-4",
        model_id="gpt-4",
        version="gpt-4-turbo",
        capabilities=["text_generation", "code", "reasoning"],
        limitations=["hallucinations", "knowledge_cutoff"],
        is_systemic_risk=True,
        flops_estimate=">10^25",
    ),
    "gemini-pro": ModelCard(
        provider="Google",
        model_name="Gemini Pro",
        model_id="gemini-pro",
        version="gemini-1.5-pro",
        capabilities=["multimodal", "long_context", "reasoning"],
        limitations=["hallucinations", "language_variance"],
        is_systemic_risk=True,
        flops_estimate=">10^25",
    ),
    "claude-3": ModelCard(
        provider="Anthropic",
        model_name="Claude 3",
        model_id="claude-3",
        version="claude-3-opus",
        capabilities=["long_context", "reasoning", "code"],
        limitations=["hallucinations", "no_web_access"],
        is_systemic_risk=True,
        flops_estimate=">10^25",
    ),
    "deepseek-chat": ModelCard(
        provider="DeepSeek",
        model_name="DeepSeek Chat",
        model_id="deepseek-chat",
        version="v3",
        capabilities=["text_generation", "code"],
        limitations=["knowledge_cutoff"],
        is_systemic_risk=False,
    ),
}


def get_model_card(model_id: str) -> ModelCard | None:
    """Get model card by ID."""
    return MODEL_REGISTRY.get(model_id)


def list_model_cards() -> list[ModelCard]:
    """List all registered model cards."""
    return list(MODEL_REGISTRY.values())


def register_model_card(card: ModelCard) -> None:
    """Register a new model card."""
    MODEL_REGISTRY[card.model_id] = card
