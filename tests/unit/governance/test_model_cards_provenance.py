"""Quick tests for Model Cards, Provenance, and Attribution.

Tasks 8, 9, 10: Model Cards, Provenance, Attribution
"""

from datetime import datetime

import pytest


class TestModelCards:
    """Test Model Cards Registry (Task 8)."""

    def test_get_model_card_gpt4(self) -> None:
        """Should retrieve GPT-4 model card."""
        from src.core.governance.model_cards import get_model_card

        card = get_model_card("gpt-4")
        assert card is not None
        assert card.provider == "OpenAI"
        assert card.is_systemic_risk is True

    def test_get_model_card_deepseek(self) -> None:
        """DeepSeek should not be systemic risk."""
        from src.core.governance.model_cards import get_model_card

        card = get_model_card("deepseek-chat")
        assert card is not None
        assert card.is_systemic_risk is False

    def test_list_model_cards(self) -> None:
        """Should list all model cards."""
        from src.core.governance.model_cards import list_model_cards

        cards = list_model_cards()
        assert len(cards) >= 4
        providers = [c.provider for c in cards]
        assert "OpenAI" in providers


class TestProvenance:
    """Test Model Provenance Tracking (Task 9)."""

    def test_log_provenance(self) -> None:
        """new_provenance_record builds a valid ProvenanceRecord without persisting."""
        from src.core.governance.model_provenance import new_provenance_record

        record = new_provenance_record(
            provider="OpenAI",
            model="gpt-4",
            model_version="gpt-4-turbo",
            input_data="Test input",
            output_data="Test output",
            tenant_id="tenant-123",
        )

        assert record.provider == "OpenAI"
        assert record.tenant_id == "tenant-123"
        assert record.retention_until is not None
        assert record.record_id != ""
        assert len(record.input_hash) == 64  # full SHA-256

    def test_provenance_hashes(self) -> None:
        """Should compute full SHA-256 content hashes (Article 53 tamper-evidence)."""
        from src.core.governance.model_provenance import compute_hash

        hash1 = compute_hash("test input")
        hash2 = compute_hash("test input")
        hash3 = compute_hash("different input")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # full 64-char hex SHA-256


class TestAttribution:
    """Test Attribution Labels (Task 10)."""

    def test_create_attribution_label(self) -> None:
        """Should create attribution label."""
        from src.core.governance.attribution import create_attribution_label

        label = create_attribution_label(
            provider="OpenAI",
            model="gpt-4",
            model_version="gpt-4-turbo",
        )

        assert label.is_ai_generated is True
        assert label.provider == "OpenAI"
        assert label.generation_timestamp is not None

    def test_attribution_to_dict(self) -> None:
        """Should convert to dictionary."""
        from src.core.governance.attribution import create_attribution_label

        label = create_attribution_label("Google", "Gemini", "v1")
        data = label.to_dict()

        assert data["ai_act_compliant"] is True
        assert data["is_ai_generated"] is True
        assert data["provider"] == "Google"

    def test_add_attribution_to_response(self) -> None:
        """Should add attribution to response data."""
        from src.core.governance.attribution import add_attribution_to_response

        response = {"text": "Generated content"}
        result = add_attribution_to_response(response, "OpenAI", "gpt-4", "turbo")

        assert "_ai_attribution" in result
        assert result["_ai_attribution"]["provider"] == "OpenAI"
