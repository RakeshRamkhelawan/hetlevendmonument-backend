"""
Unhappy Path Tests for Agentic Services

Tests edge cases, error scenarios, and invalid inputs to ensure
the stack is robust and handles failures gracefully.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# LocaleManager Unhappy Path Tests
# =============================================================================


class TestLocaleManagerUnhappyPaths:
    """Test LocaleManager error handling and edge cases."""

    @pytest.fixture
    def locale_manager(self):
        from src.domains.agentic.services.locale_manager import LocaleManager

        return LocaleManager()

    # --- Invalid Locale Handling ---

    def test_empty_string_locale_returns_default(self, locale_manager):
        """Empty string locale should return default 'en'."""
        result = locale_manager.get_effective_locale(user_locale="", tenant_locale="")
        assert result == "en"

    def test_none_locale_returns_default(self, locale_manager):
        """None locale should return default 'en'."""
        result = locale_manager.get_effective_locale(user_locale=None, tenant_locale=None)
        assert result == "en"

    def test_invalid_locale_code_returns_default(self, locale_manager):
        """Invalid locale codes should fall back to default."""
        invalid_locales = ["xyz", "123", "!@#$", "en_", "_US", "verylonginvalidlocale"]
        for invalid in invalid_locales:
            result = locale_manager.get_effective_locale(user_locale=invalid, tenant_locale=None)
            assert result == "en", f"Invalid locale '{invalid}' should return 'en'"

    def test_partial_locale_extraction(self, locale_manager):
        """Should extract base locale from full codes like 'nl_NL'."""
        result = locale_manager.get_effective_locale(user_locale="nl_NL", tenant_locale=None)
        assert result == "nl"

        result = locale_manager.get_effective_locale(user_locale="hi_IN", tenant_locale=None)
        assert result == "hi"

    # --- Prompt Localization Edge Cases ---

    def test_localize_prompt_with_none_template(self, locale_manager):
        """Should handle None template gracefully."""
        with pytest.raises((AttributeError, TypeError)):
            locale_manager.localize_prompt(None, "nl")

    def test_localize_prompt_with_missing_system_prompt(self, locale_manager):
        """Template without system_prompt should raise or handle gracefully."""
        template = MagicMock()
        template.system_prompt = None
        template.localized_variants = None

        # Should not crash, return None or empty
        result = locale_manager.localize_prompt(template, "nl")
        assert result is None or result == ""

    def test_localize_prompt_with_malformed_variants(self, locale_manager):
        """Malformed localized_variants should not crash."""
        template = MagicMock()
        template.system_prompt = "Default"
        template.localized_variants = "not a dict"  # Invalid type

        # Should fall back to default
        result = locale_manager.localize_prompt(template, "nl")
        assert result == "Default"

    def test_localize_prompt_with_partial_variant(self, locale_manager):
        """Variant without system_prompt key should fall back."""
        template = MagicMock()
        template.system_prompt = "Default prompt"
        template.localized_variants = {"nl": {"other_field": "value"}}  # Missing system_prompt

        result = locale_manager.localize_prompt(template, "nl")
        assert result == "Default prompt"

    # --- Feature Intent Keywords Edge Cases ---

    def test_get_intent_keywords_with_none_feature(self, locale_manager):
        """Should handle None feature gracefully."""
        with pytest.raises((AttributeError, TypeError)):
            locale_manager.get_intent_keywords(None, "en")

    def test_get_intent_keywords_with_string_instead_of_list(self, locale_manager):
        """Should handle malformed intent_keywords (string instead of list)."""
        feature = MagicMock()
        feature.intent_keywords = "not a dict"

        result = locale_manager.get_intent_keywords(feature, "en")
        # Should return empty list or handle gracefully
        assert isinstance(result, list)

    # --- Formatting Edge Cases ---

    def test_format_date_with_none(self, locale_manager):
        """Should handle None date."""
        with pytest.raises((AttributeError, TypeError)):
            locale_manager.format_date(None, "en")

    def test_format_number_with_none(self, locale_manager):
        """Should handle None number."""
        with pytest.raises((TypeError, AttributeError)):
            locale_manager.format_number(None, "en")

    def test_format_number_with_string(self, locale_manager):
        """Should handle string input gracefully."""
        with pytest.raises((TypeError, ValueError)):
            locale_manager.format_number("not a number", "en")

    def test_format_date_with_invalid_locale(self, locale_manager):
        """Invalid locale should use default format."""
        date = datetime(2026, 2, 3)
        result = locale_manager.format_date(date, "invalid_locale")
        # Should not crash, should use some format
        assert "2026" in result


# =============================================================================
# AgentMetricsCollector Unhappy Path Tests
# =============================================================================


class TestMetricsCollectorUnhappyPaths:
    """Test AgentMetricsCollector error handling and edge cases."""

    @pytest.fixture
    def metrics_collector(self):
        from src.domains.agentic.services.metrics_collector import AgentMetricsCollector

        return AgentMetricsCollector()

    # --- Invalid Input Handling ---

    def test_record_chat_request_with_none_feature(self, metrics_collector):
        """Should handle None feature gracefully."""
        # Should not crash, but may log warning
        metrics_collector.record_chat_request(
            feature=None, tenant_id="tenant_1", duration=0.5, success=True
        )
        # Verify no exception raised

    def test_record_chat_request_with_empty_strings(self, metrics_collector):
        """Should handle empty string values."""
        metrics_collector.record_chat_request(feature="", tenant_id="", duration=0.5, success=True)
        # Should not crash

    def test_record_chat_request_with_negative_duration(self, metrics_collector):
        """Should handle negative duration values."""
        metrics_collector.record_chat_request(
            feature="assistant",
            tenant_id="tenant_1",
            duration=-1.0,
            success=True,  # Invalid
        )
        # Should not crash, Prometheus will accept it

    def test_record_chat_request_with_very_large_duration(self, metrics_collector):
        """Should handle extremely large duration values."""
        metrics_collector.record_chat_request(
            feature="assistant",
            tenant_id="tenant_1",
            duration=float("inf"),  # Edge case
            success=True,
        )
        # Should not crash

    # --- Token Usage Edge Cases ---

    def test_record_token_usage_with_negative_tokens(self, metrics_collector):
        """Should handle negative token counts."""
        metrics_collector.record_token_usage(
            feature="assistant", input_tokens=-100, output_tokens=-50
        )
        # Should not crash

    def test_record_token_usage_with_zero_tokens(self, metrics_collector):
        """Should handle zero token counts."""
        metrics_collector.record_token_usage(feature="assistant", input_tokens=0, output_tokens=0)
        # Valid case, should work

    def test_record_token_usage_with_very_large_tokens(self, metrics_collector):
        """Should handle very large token counts."""
        metrics_collector.record_token_usage(
            feature="assistant",
            input_tokens=10**9,
            output_tokens=10**9,  # 1 billion tokens
        )
        # Should not crash

    # --- Satisfaction Score Edge Cases ---

    def test_record_satisfaction_below_range(self, metrics_collector):
        """Scores below 1 should be clamped or handled."""
        metrics_collector.record_satisfaction(feature="assistant", variant="v1", score=0)
        metrics_collector.record_satisfaction(feature="assistant", variant="v1", score=-5)
        # Should not crash, score should be clamped to 1

    def test_record_satisfaction_above_range(self, metrics_collector):
        """Scores above 5 should be clamped or handled."""
        metrics_collector.record_satisfaction(feature="assistant", variant="v1", score=10)
        metrics_collector.record_satisfaction(feature="assistant", variant="v1", score=100)
        # Should not crash, score should be clamped to 5

    def test_record_satisfaction_with_none_score(self, metrics_collector):
        """Should handle None score - raises TypeError due to min/max comparison."""
        # min() and max() with None will raise TypeError
        with pytest.raises(TypeError):
            metrics_collector.record_satisfaction(feature="assistant", variant="v1", score=None)

    # --- Feature Detection Edge Cases ---

    def test_record_feature_detection_invalid_layer(self, metrics_collector):
        """Should handle invalid detection layer names."""
        metrics_collector.record_feature_detection(layer="invalid_layer")
        metrics_collector.record_feature_detection(layer="")
        metrics_collector.record_feature_detection(layer="123")
        # Should not crash, may record as "unknown"

    def test_record_feature_detection_none_layer(self, metrics_collector):
        """Should handle None layer."""
        # May raise or handle gracefully
        try:
            metrics_collector.record_feature_detection(layer=None)
        except (TypeError, AttributeError):
            pass  # Expected

    # --- Active Sessions Edge Cases ---

    def test_update_active_sessions_negative_count(self, metrics_collector):
        """Should handle negative session counts."""
        metrics_collector.update_active_sessions(tenant_id="tenant_1", count=-5)
        # Gauge can accept negative values technically

    def test_update_active_sessions_zero_count(self, metrics_collector):
        """Zero sessions is valid."""
        metrics_collector.update_active_sessions(tenant_id="tenant_1", count=0)
        # Should work normally


# =============================================================================
# Seed Data Unhappy Path Tests
# =============================================================================


class TestSeedDataUnhappyPaths:
    """Test seed data validation for edge cases.

    Note: SQLAlchemy models don't validate at instantiation time.
    Validation happens at database commit with constraints.
    These tests verify that models can be instantiated (even with partial data)
    without crashing - actual validation is DB-level.
    """

    def test_feature_with_partial_fields_is_valid_object(self):
        """Feature can be instantiated with partial fields for ORM flexibility."""
        from src.domains.agentic.models import Feature

        # SQLAlchemy allows partial instantiation - DB constraints validate
        feature = Feature(id="test_feature")
        assert feature.id == "test_feature"
        # name, description, category will be None - DB constraint validates

    def test_tool_with_partial_fields_is_valid_object(self):
        """ToolDefinition can be instantiated with partial fields."""
        from src.domains.agentic.models import ToolDefinition

        # SQLAlchemy allows partial instantiation
        tool = ToolDefinition(name="test_tool")
        assert tool.name == "test_tool"
        # function_schema will be None - DB constraint validates at commit

    def test_prompt_template_with_invalid_status(self):
        """PromptTemplate accepts any status string at model level."""
        from src.domains.agentic.models import PromptTemplate

        # This succeeds - DB constraints or business logic validate
        template = PromptTemplate(
            name="test",
            version="1.0.0",
            system_prompt="Test prompt",
            status="invalid_status_value",
        )
        assert template.status == "invalid_status_value"


# =============================================================================
# Cross-Service Integration Unhappy Paths
# =============================================================================


class TestCrossServiceUnhappyPaths:
    """Test unhappy paths when services interact."""

    @pytest.fixture
    def locale_manager(self):
        from src.domains.agentic.services.locale_manager import LocaleManager

        return LocaleManager()

    @pytest.fixture
    def metrics_collector(self):
        from src.domains.agentic.services.metrics_collector import AgentMetricsCollector

        return AgentMetricsCollector()

    def test_metrics_with_localized_feature_names(self, locale_manager, metrics_collector):
        """Metrics should handle Unicode feature names from localization."""
        # Get Hindi feature name
        feature = MagicMock()
        feature.id = "assistant"
        feature.intent_keywords = {"hi": ["मदद"]}

        keywords = locale_manager.get_intent_keywords(feature, "hi")

        # Record metric with Unicode
        metrics_collector.record_chat_request(
            feature="assistant_hindi_मदद",
            tenant_id="tenant_1",
            duration=0.5,
            success=True,
        )
        # Should not crash

    def test_extreme_concurrent_metrics_recording(self, metrics_collector):
        """Should handle rapid consecutive metric recordings."""
        for i in range(1000):
            metrics_collector.record_chat_request(
                feature=f"feature_{i % 10}",
                tenant_id=f"tenant_{i % 5}",
                duration=0.001 * i,
                success=i % 2 == 0,
            )
        # Should not crash or timeout

    def test_locale_and_metrics_with_special_characters(self, locale_manager, metrics_collector):
        """Should handle special characters in labels."""
        special_strings = [
            "feature with spaces",
            "feature-with-dashes",
            "feature_with_underscores",
            "feature.with.dots",
            "feature:with:colons",
        ]

        for feature in special_strings:
            metrics_collector.record_chat_request(
                feature=feature, tenant_id="tenant_1", duration=0.1, success=True
            )
        # Should not crash
