"""Tests for Public Documentation Generator.

EU AI Act Compliance - Task 7: Article 53 Public Documentation
Tests for generating markdown documentation for GPAI systems.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest


class TestPublicDocumentationGenerator:
    """Test public documentation generation."""

    def test_generate_model_documentation(self) -> None:
        """Should generate markdown documentation for a model."""
        from src.core.governance.public_docs import generate_model_documentation

        model_info = {
            "provider": "OpenAI",
            "model_name": "GPT-4",
            "version": "gpt-4-0125-preview",
            "capabilities": ["text_generation", "code_generation", "analysis"],
            "limitations": ["may_hallucinate", "knowledge_cutoff_2024"],
            "training_data_summary": "Trained on diverse internet text up to 2024",
            "is_systemic_risk": True,
        }

        doc = generate_model_documentation(model_info)

        assert "# GPT-4" in doc
        assert "## Capabilities" in doc
        assert "## Limitations" in doc
        assert "text_generation" in doc
        assert "OpenAI" in doc

    def test_documentation_includes_systemic_risk_flag(self) -> None:
        """Documentation should indicate systemic risk models."""
        from src.core.governance.public_docs import generate_model_documentation

        model_info = {
            "provider": "Google",
            "model_name": "Gemini Pro",
            "is_systemic_risk": True,
        }

        doc = generate_model_documentation(model_info)

        assert "systemic risk" in doc.lower() or "Article 55" in doc

    def test_generate_all_models_documentation(self) -> None:
        """Should generate docs for all registered models."""
        from src.core.governance.public_docs import generate_all_models_documentation

        docs = generate_all_models_documentation()

        assert isinstance(docs, dict)
        assert len(docs) > 0
        # Should include at least DeepSeek, OpenAI, Google, Anthropic
        providers = [doc.get("provider", "").lower() for doc in docs.values()]
        assert any("openai" in p for p in providers)


class TestModelCardIntegration:
    """Test integration with Model Cards."""

    def test_documentation_uses_model_card_data(self) -> None:
        """Documentation should pull from ModelCard registry."""
        from src.core.governance.public_docs import get_model_card_docs

        docs = get_model_card_docs("gpt-4")

        assert docs is not None
        assert "gpt" in docs.get("model_name", "").lower()

    def test_documentation_for_unknown_model(self) -> None:
        """Should handle unknown models gracefully."""
        from src.core.governance.public_docs import get_model_card_docs

        docs = get_model_card_docs("unknown-model")

        assert docs is None or docs == {}


class TestDocumentationCompliance:
    """Test Article 53 compliance requirements."""

    def test_documentation_includes_all_article_53_elements(self) -> None:
        """Documentation should include all Article 53 required elements."""
        from src.core.governance.public_docs import generate_model_documentation

        model_info = {
            "provider": "TestProvider",
            "model_name": "TestModel",
            "capabilities": ["test"],
            "limitations": ["test_limitation"],
            "training_data_summary": "Test training data",
            "intended_use_cases": ["testing"],
            "out_of_scope_uses": ["harmful activities"],
            "performance_metrics": {"accuracy": 0.95},
        }

        doc = generate_model_documentation(model_info)
        doc_lower = doc.lower()

        # Check key Article 53 elements are present
        assert "provider" in doc_lower
        assert "capabilities" in doc_lower
        assert "limitations" in doc_lower
        assert "training" in doc_lower or "data" in doc_lower
        assert "intended" in doc_lower or "use" in doc_lower
        assert "out-of-scope" in doc_lower or "scope" in doc_lower

    def test_documentation_is_exportable(self, tmp_path: Path) -> None:
        """Documentation should be exportable as markdown.

        `output_dir` is expliciet, want de default is `docs/ai_act` -- de echte, getrackte
        map in de repo. Zonder deze parameter herschreef elke suite-run
        `docs/ai_act/gpa_model_documentation.md` met een nieuwe tijdstempel, waardoor
        `git status` na iedere run vuil was en de "Generated"-datum in dat AI Act-artefact
        niets meer betekende. Dat is minstens sinds april 2026 in zes sprint-briefs
        afgedaan als "pre-existing rommel" (BE-AGT-043).
        """
        from src.core.governance.public_docs import export_documentation

        result = export_documentation(format="markdown", output_dir=str(tmp_path))

        assert Path(result).parent == tmp_path, (
            "De export moet in de meegegeven map landen; anders schrijft deze test weer in "
            "de getrackte repo-tree."
        )
        assert Path(result).suffix == ".md"
        assert Path(result).read_text(encoding="utf-8").strip(), "export mag niet leeg zijn"
