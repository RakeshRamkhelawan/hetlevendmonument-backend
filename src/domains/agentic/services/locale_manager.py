"""
LocaleManager Service for Agentic Domain

Handles locale resolution, prompt localization, and locale-aware formatting.

Priority chain for locale resolution:
1. User's preferred_locale
2. Tenant's primary_locale
3. System default ("en")
"""

import logging
from datetime import datetime
from typing import Any, Optional

from src.domains.agentic.models import Feature, PromptTemplate

logger = logging.getLogger(__name__)


class LocaleManager:
    """
    Service for managing localization in the agentic domain.

    Responsibilities:
    - Resolve effective locale from user/tenant/system defaults
    - Localize prompt templates to target locale
    - Provide locale-aware formatting (dates, numbers)
    - Return intent keywords for feature detection
    """

    # Supported locales (ISO 639-1 codes)
    SUPPORTED_LOCALES = ["en", "nl", "hi", "sa"]
    DEFAULT_LOCALE = "en"

    # Locale-specific date formats
    DATE_FORMATS = {
        "en": "%B %d, %Y",  # February 03, 2026
        "nl": "%d-%m-%Y",  # 03-02-2026
        "hi": "%d/%m/%Y",  # 03/02/2026
        "sa": "%d/%m/%Y",  # 03/02/2026
    }

    # Decimal separators per locale
    DECIMAL_SEPARATORS = {
        "en": ".",
        "nl": ",",
        "hi": ".",
        "sa": ".",
    }

    # Thousands separators per locale
    THOUSANDS_SEPARATORS = {
        "en": ",",
        "nl": ".",
        "hi": ",",
        "sa": ",",
    }

    def __init__(self) -> None:
        """Initialize the LocaleManager."""
        logger.debug("LocaleManager initialized")

    def get_supported_locales(self) -> list[str]:
        """Get list of supported locale codes."""
        return self.SUPPORTED_LOCALES.copy()

    def is_valid_locale(self, locale: str) -> bool:
        """Check if a locale is supported."""
        if not locale:
            return False
        # Handle full locale codes like "en_US" -> "en"
        base_locale = locale.split("_")[0].lower()
        return base_locale in self.SUPPORTED_LOCALES

    def normalize_locale(self, locale: str) -> str:
        """Normalize locale to base code (e.g., 'en_US' -> 'en')."""
        if not locale:
            return self.DEFAULT_LOCALE
        base_locale = locale.split("_")[0].lower()
        if base_locale in self.SUPPORTED_LOCALES:
            return base_locale
        return self.DEFAULT_LOCALE

    def get_effective_locale(
        self, user_locale: str | None = None, tenant_locale: str | None = None
    ) -> str:
        """
        Resolve the effective locale using priority chain.

        Priority:
        1. User's preferred_locale (if valid)
        2. Tenant's primary_locale (if valid)
        3. System default ("en")

        Args:
            user_locale: User's preferred locale
            tenant_locale: Tenant's primary locale

        Returns:
            Effective locale code (e.g., "nl", "en", "hi")
        """
        # Try user locale first
        if user_locale and self.is_valid_locale(user_locale):
            return self.normalize_locale(user_locale)

        # Fall back to tenant locale
        if tenant_locale and self.is_valid_locale(tenant_locale):
            return self.normalize_locale(tenant_locale)

        # System default
        return self.DEFAULT_LOCALE

    def localize_prompt(self, template: PromptTemplate, locale: str) -> str:
        """
        Get the localized system prompt for a template.

        If the requested locale has a variant in localized_variants,
        return that. Otherwise, return the default system_prompt.

        Args:
            template: PromptTemplate model instance
            locale: Target locale code

        Returns:
            Localized system prompt string
        """
        # Normalize locale
        locale = self.normalize_locale(locale)

        # If English or no variants, return default
        if locale == "en":
            return template.system_prompt

        # Check for localized variants
        variants: dict[str, Any] = template.localized_variants  # type: ignore[assignment]
        if not variants:
            return template.system_prompt

        # Look for locale-specific variant
        if locale in variants and "system_prompt" in variants[locale]:
            return str(variants[locale]["system_prompt"])

        # Fall back to default
        return template.system_prompt

    def get_intent_keywords(self, feature: Feature, locale: str) -> list[str]:
        """
        Get intent detection keywords for a feature in the specified locale.

        Args:
            feature: Feature model instance
            locale: Target locale code

        Returns: List[Any] of keywords for intent detection  # TODO(TYPE): replace Any with concrete type
        """
        # Normalize locale
        locale = self.normalize_locale(locale)

        # Get intent_keywords dict
        keywords: dict[str, Any] = feature.intent_keywords  # type: ignore[assignment]
        if not keywords:
            return []

        # Try exact locale match
        if locale in keywords:
            return list(keywords[locale])

        # Fall back to English
        if "en" in keywords:
            return list(keywords["en"])

        # No keywords available
        return []

    def format_date(self, date: datetime, locale: str) -> str:
        """
        Format a datetime according to locale conventions.

        Args:
            date: Datetime to format
            locale: Target locale code

        Returns:
            Formatted date string
        """
        locale = self.normalize_locale(locale)
        fmt = self.DATE_FORMATS.get(locale, self.DATE_FORMATS["en"])
        return date.strftime(fmt)

    def format_number(self, number: float, locale: str) -> str:
        """
        Format a number according to locale conventions.

        Args:
            number: Number to format
            locale: Target locale code

        Returns:
            Formatted number string
        """
        locale = self.normalize_locale(locale)

        decimal_sep = self.DECIMAL_SEPARATORS.get(locale, ".")
        thousands_sep = self.THOUSANDS_SEPARATORS.get(locale, ",")

        # Split into integer and decimal parts
        if isinstance(number, float):
            int_part = int(number)
            dec_part = abs(number - int_part)
            dec_str = f"{dec_part:.2f}"[2:]  # Get decimal digits
        else:
            int_part = int(number)
            dec_str = "00"

        # Format integer part with thousands separator
        int_str = f"{abs(int_part):,}".replace(",", thousands_sep)

        # Handle negative numbers
        sign = "-" if number < 0 else ""

        return f"{sign}{int_str}{decimal_sep}{dec_str}"


# Singleton instance for convenience
locale_manager = LocaleManager()
