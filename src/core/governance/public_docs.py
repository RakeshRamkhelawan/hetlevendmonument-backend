"""Public Documentation Generator for EU AI Act compliance.

Task 7: Article 53 GPAI Technical Documentation
Generates markdown documentation for GPAI model providers.

Reference: Regulation (EU) 2024/1689 Article 53
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Article 53 required documentation elements
ARTICLE_53_REQUIRED_ELEMENTS = [
    "provider",
    "capabilities",
    "limitations",
    "training_data",
    "intended_use",
    "out_of_scope",
]


@dataclass
class ModelDocumentation:
    """Documentation for a GPAI model per Article 53.

    Attributes:
        provider: Model provider organization
        model_name: Model name
        version: Model version
        capabilities: List of capabilities
        limitations: List of known limitations
        training_data_summary: Summary of training data
        intended_use_cases: Intended use cases
        out_of_scope_uses: Out-of-scope use cases
        performance_metrics: Performance metrics
        is_systemic_risk: Whether model has systemic risk
        flops_estimate: Estimated FLOPs for training
    """

    provider: str
    model_name: str
    version: str = ""
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    training_data_summary: str = ""
    intended_use_cases: list[str] = field(default_factory=list)
    out_of_scope_uses: list[str] = field(default_factory=list)
    performance_metrics: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    is_systemic_risk: bool = False
    flops_estimate: str | None = None

    def to_markdown(self) -> str:
        """Generate markdown documentation."""
        lines = [
            f"# {self.model_name}",
            "",
            f"**Provider:** {self.provider}",
        ]

        if self.version:
            lines.append(f"**Version:** {self.version}")

        if self.is_systemic_risk:
            lines.extend(
                [
                    "",
                    "> [WARN] **Systemic Risk Model (Article 55)**",
                    "> This model has been classified as having systemic risk under EU AI Act Article 55.",
                ]
            )

        lines.extend(
            [
                "",
                "## Capabilities",
                "",
            ]
        )

        for capability in self.capabilities:
            lines.append(f"- {capability}")

        lines.extend(
            [
                "",
                "## Limitations",
                "",
            ]
        )

        for limitation in self.limitations:
            lines.append(f"- {limitation}")

        if self.training_data_summary:
            lines.extend(
                [
                    "",
                    "## Training Data",
                    "",
                    self.training_data_summary,
                ]
            )

        if self.intended_use_cases:
            lines.extend(
                [
                    "",
                    "## Intended Use Cases",
                    "",
                ]
            )
            for use_case in self.intended_use_cases:
                lines.append(f"- {use_case}")

        if self.out_of_scope_uses:
            lines.extend(
                [
                    "",
                    "## Out-of-Scope Uses",
                    "",
                ]
            )
            for use_case in self.out_of_scope_uses:
                lines.append(f"- {use_case}")

        if self.performance_metrics:
            lines.extend(
                [
                    "",
                    "## Performance Metrics",
                    "",
                ]
            )
            for metric, value in self.performance_metrics.items():
                lines.append(f"- **{metric}:** {value}")

        lines.extend(
            [
                "",
                "---",
                "",
                "*Documentation generated per EU AI Act Article 53*",
                f"*Generated: {datetime.now(timezone.utc).isoformat()}*",
            ]
        )

        return "\n".join(lines)


# Pre-defined model documentation per provider
DEFAULT_MODEL_DOCS: dict[str, ModelDocumentation] = {
    "gpt-4": ModelDocumentation(
        provider="OpenAI",
        model_name="GPT-4",
        version="gpt-4-turbo",
        capabilities=[
            "Text generation and completion",
            "Code generation and analysis",
            "Reasoning and problem solving",
            "Multi-turn conversation",
        ],
        limitations=[
            "May generate incorrect or misleading information",
            "Knowledge cutoff date (April 2024)",
            "Can be sensitive to prompt phrasing",
            "May exhibit biases present in training data",
        ],
        training_data_summary="Trained on diverse internet text, books, and code repositories up to April 2024",
        intended_use_cases=[
            "Content generation",
            "Code assistance",
            "Analysis and research",
            "Educational applications",
        ],
        out_of_scope_uses=[
            "Medical diagnosis",
            "Legal advice without verification",
            "Critical infrastructure decisions without oversight",
        ],
        is_systemic_risk=True,
        flops_estimate=">10^25 FLOPs",
    ),
    "gemini-pro": ModelDocumentation(
        provider="Google",
        model_name="Gemini Pro",
        version="gemini-1.5-pro",
        capabilities=[
            "Multimodal understanding (text, image, video)",
            "Long context window (1M+ tokens)",
            "Code generation",
            "Reasoning tasks",
        ],
        limitations=[
            "May hallucinate or generate incorrect information",
            "Training data has cutoff date",
            "Performance varies by language",
        ],
        training_data_summary="Trained on multimodal web documents, books, code, and images",
        intended_use_cases=[
            "Document analysis",
            "Code generation",
            "Multimodal reasoning",
        ],
        out_of_scope_uses=[
            "Autonomous decision making without oversight",
            "Medical or legal decisions without verification",
        ],
        is_systemic_risk=True,
        flops_estimate=">10^25 FLOPs",
    ),
    "claude-3": ModelDocumentation(
        provider="Anthropic",
        model_name="Claude 3",
        version="claude-3-opus",
        capabilities=[
            "Long context processing (200K tokens)",
            "Reasoning and analysis",
            "Code generation",
            "Instruction following",
        ],
        limitations=[
            "May generate incorrect information",
            "Knowledge cutoff date",
            "Cannot access external websites",
        ],
        training_data_summary="Trained on diverse text corpora with constitutional AI alignment",
        intended_use_cases=[
            "Research assistance",
            "Content analysis",
            "Code review",
        ],
        out_of_scope_uses=[
            "High-stakes decisions without verification",
            "Autonomous agent operations",
        ],
        is_systemic_risk=True,
        flops_estimate=">10^25 FLOPs",
    ),
    "deepseek-chat": ModelDocumentation(
        provider="DeepSeek",
        model_name="DeepSeek Chat",
        version="deepseek-v3",
        capabilities=[
            "Text generation",
            "Code generation",
            "Reasoning",
        ],
        limitations=[
            "Knowledge cutoff limitations",
            "May generate incorrect information",
        ],
        training_data_summary="Trained on diverse text and code datasets",
        intended_use_cases=[
            "General text generation",
            "Code assistance",
        ],
        out_of_scope_uses=[
            "Critical decisions without human review",
        ],
        is_systemic_risk=False,
    ),
}


def generate_model_documentation(model_info: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Generate markdown documentation for a model.

    Args:
        model_info: Dictionary with model information

    Returns:
        Markdown documentation string
    """
    doc = ModelDocumentation(
        provider=model_info.get("provider", "Unknown"),
        model_name=model_info.get("model_name", "Unknown"),
        version=model_info.get("version", ""),
        capabilities=model_info.get("capabilities", []),
        limitations=model_info.get("limitations", []),
        training_data_summary=model_info.get("training_data_summary", ""),
        intended_use_cases=model_info.get("intended_use_cases", []),
        out_of_scope_uses=model_info.get("out_of_scope_uses", []),
        performance_metrics=model_info.get("performance_metrics", {}),
        is_systemic_risk=model_info.get("is_systemic_risk", False),
        flops_estimate=model_info.get("flops_estimate"),
    )

    return doc.to_markdown()


def generate_all_models_documentation() -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Generate documentation for all registered models.

    Returns:
        Dictionary mapping model IDs to documentation
    """
    result = {}
    for model_id, doc in DEFAULT_MODEL_DOCS.items():
        result[model_id] = {
            "provider": doc.provider,
            "model_name": doc.model_name,
            "version": doc.version,
            "is_systemic_risk": doc.is_systemic_risk,
            "documentation": doc.to_markdown(),
        }
    return result


def get_model_card_docs(model_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
    """Get documentation for a specific model.

    Args:
        model_id: Model identifier

    Returns:
        Model documentation or None if not found
    """
    doc = DEFAULT_MODEL_DOCS.get(model_id)
    if doc:
        return {
            "provider": doc.provider,
            "model_name": doc.model_name,
            "version": doc.version,
            "is_systemic_risk": doc.is_systemic_risk,
            "documentation": doc.to_markdown(),
        }
    return None


def export_documentation(
    format: str = "markdown",
    output_dir: str = "docs/ai_act",
) -> str:
    """Export all documentation to files.

    Args:
        format: Output format (currently only "markdown")
        output_dir: Output directory

    Returns:
        Path to generated file
    """
    os.makedirs(output_dir, exist_ok=True)

    if format == "markdown":
        output_path = os.path.join(output_dir, "gpa_model_documentation.md")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# GPAI Model Documentation\n\n")
            f.write("*Generated per EU AI Act Article 53*\n\n")
            f.write("---\n\n")

            for model_id, doc in DEFAULT_MODEL_DOCS.items():
                f.write(doc.to_markdown())
                f.write("\n\n---\n\n")

        return output_path

    raise ValueError(f"Unsupported format: {format}")
