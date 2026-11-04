"""
TDD Red Phase Tests for LocaleManager Service

These tests define the expected behavior of the LocaleManager.
They should FAIL initially until the service is implemented.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import models for type hints
from src.domains.agentic.models import Feature, PromptTemplate

# =============================================================================
# LocaleManager Interface Tests
# =============================================================================


class TestLocaleResolution:
    """Test locale resolution priority: user → tenant → system default."""

    @pytest.fixture
    def locale_manager(self):
        """Import LocaleManager - will fail until implemented."""
        from src.domains.agentic.services.locale_manager import LocaleManager

        return LocaleManager()

    def test_user_locale_overrides_tenant(self, locale_manager):
        """User's preferred_locale should override tenant's primary_locale."""
        # User prefers Dutch, tenant default is English
        user_locale = "nl"
        tenant_locale = "en"

        effective = locale_manager.get_effective_locale(
            user_locale=user_locale, tenant_locale=tenant_locale
        )

        assert effective == "nl", "User locale should take priority"

    def test_tenant_locale_used_when_user_none(self, locale_manager):
        """Tenant's primary_locale should be used when user has no preference."""
        user_locale = None
        tenant_locale = "hi"

        effective = locale_manager.get_effective_locale(
            user_locale=user_locale, tenant_locale=tenant_locale
        )

        assert effective == "hi", "Tenant locale should be used as fallback"

    def test_system_default_when_both_none(self, locale_manager):
        """System default 'en' should be used when both user and tenant are None."""
        effective = locale_manager.get_effective_locale(user_locale=None, tenant_locale=None)

        assert effective == "en", "System default 'en' should be fallback"

    def test_invalid_locale_falls_back_to_default(self, locale_manager):
        """Invalid locale codes should fall back to system default."""
        effective = locale_manager.get_effective_locale(
            user_locale="xx_XX",
            tenant_locale=None,  # Invalid locale
        )

        assert effective == "en", "Invalid locale should fall back to 'en'"

    def test_supported_locales_validation(self, locale_manager):
        """Only supported locales should be accepted."""
        supported = locale_manager.get_supported_locales()

        assert "en" in supported
        assert "nl" in supported
        assert "hi" in supported
        assert len(supported) >= 3


# =============================================================================
# Prompt Template Localization Tests
# =============================================================================


class TestPromptLocalization:
    """Test prompt template localization behavior."""

    @pytest.fixture
    def locale_manager(self):
        from src.domains.agentic.services.locale_manager import LocaleManager

        return LocaleManager()

    @pytest.fixture
    def mock_template(self):
        """Create a mock PromptTemplate with localized variants."""
        template = MagicMock(spec=PromptTemplate)
        template.name = "general_assistant_v1"
        template.system_prompt = "You are a helpful AI assistant."
        template.localized_variants = {
            "nl": {"system_prompt": "Je bent een behulpzame AI-assistent."},
            "hi": {"system_prompt": "आप एक सहायक AI सहायक हैं।"},
        }
        return template

    def test_localize_prompt_returns_dutch_for_nl(self, locale_manager, mock_template):
        """Localize prompt should return Dutch system_prompt for nl locale."""
        localized = locale_manager.localize_prompt(mock_template, "nl")

        assert "behulpzame" in localized, "Should contain Dutch text"
        assert "helpful" not in localized.lower(), "Should not contain English fallback"

    def test_localize_prompt_returns_hindi_for_hi(self, locale_manager, mock_template):
        """Localize prompt should return Hindi system_prompt for hi locale."""
        localized = locale_manager.localize_prompt(mock_template, "hi")

        assert "सहायक" in localized, "Should contain Hindi text"

    def test_localize_prompt_falls_back_for_missing_locale(self, locale_manager, mock_template):
        """Missing locale should fall back to default system_prompt."""
        localized = locale_manager.localize_prompt(mock_template, "fr")  # French not available

        assert "helpful" in localized.lower(), "Should fall back to English"

    def test_localize_prompt_returns_default_for_en(self, locale_manager, mock_template):
        """English locale should return the default system_prompt."""
        localized = locale_manager.localize_prompt(mock_template, "en")

        assert localized == "You are a helpful AI assistant."

    def test_localize_prompt_handles_empty_variants(self, locale_manager):
        """Empty localized_variants should return default prompt."""
        template = MagicMock(spec=PromptTemplate)
        template.system_prompt = "Default prompt"
        template.localized_variants = {}

        localized = locale_manager.localize_prompt(template, "nl")

        assert localized == "Default prompt"

    def test_localize_prompt_handles_none_variants(self, locale_manager):
        """None localized_variants should return default prompt."""
        template = MagicMock(spec=PromptTemplate)
        template.system_prompt = "Default prompt"
        template.localized_variants = None

        localized = locale_manager.localize_prompt(template, "nl")

        assert localized == "Default prompt"


# =============================================================================
# Feature Localization Tests
# =============================================================================


class TestFeatureLocalization:
    """Test feature name and description localization."""

    @pytest.fixture
    def locale_manager(self):
        from src.domains.agentic.services.locale_manager import LocaleManager

        return LocaleManager()

    @pytest.fixture
    def mock_feature(self):
        """Create a mock Feature with intent_keywords per locale."""
        feature = MagicMock(spec=Feature)
        feature.id = "assistant"
        feature.name = "General Assistant"
        feature.description = "A helpful AI assistant"
        feature.intent_keywords = {
            "en": ["help", "question", "what is"],
            "nl": ["help", "vraag", "wat is"],
            "hi": ["मदद", "सवाल", "क्या है"],
        }
        return feature

    def test_get_intent_keywords_for_locale(self, locale_manager, mock_feature):
        """Get intent keywords for specific locale."""
        keywords = locale_manager.get_intent_keywords(mock_feature, "nl")

        assert "vraag" in keywords
        assert "wat is" in keywords

    def test_get_intent_keywords_falls_back_to_en(self, locale_manager, mock_feature):
        """Missing locale should fall back to English keywords."""
        keywords = locale_manager.get_intent_keywords(mock_feature, "fr")

        assert "help" in keywords
        assert "question" in keywords

    def test_get_intent_keywords_empty_for_no_data(self, locale_manager):
        """Empty intent_keywords should return empty list."""
        feature = MagicMock(spec=Feature)
        feature.intent_keywords = None

        keywords = locale_manager.get_intent_keywords(feature, "en")

        assert keywords == []


# =============================================================================
# Formatting Tests
# =============================================================================


class TestLocaleFormatting:
    """Test locale-aware formatting for dates and numbers."""

    @pytest.fixture
    def locale_manager(self):
        from src.domains.agentic.services.locale_manager import LocaleManager

        return LocaleManager()

    def test_format_date_dutch(self, locale_manager):
        """Dutch date format should be DD-MM-YYYY."""
        date = datetime(2026, 2, 3, 10, 30)
        formatted = locale_manager.format_date(date, "nl")

        # Dutch uses day-month-year format
        assert "3" in formatted and "2" in formatted and "2026" in formatted

    def test_format_date_english(self, locale_manager):
        """English date format should be readable."""
        date = datetime(2026, 2, 3, 10, 30)
        formatted = locale_manager.format_date(date, "en")

        assert "2026" in formatted

    def test_format_number_with_locale(self, locale_manager):
        """Numbers should be formatted according to locale."""
        number = 1234567.89

        # Dutch uses comma as decimal separator
        formatted_nl = locale_manager.format_number(number, "nl")
        # English uses period as decimal separator
        formatted_en = locale_manager.format_number(number, "en")

        # Both should contain the digits
        assert (
            "1234567" in formatted_nl.replace(".", "").replace(",", "")
            or "1.234.567" in formatted_nl
            or "1,234,567" in formatted_nl
        )
