"""
DeepSeek provider detection for the enterprise LLM factory.

Findings: LLM-ADR26-003
"""

import pytest

from src.core.llm.provider_factory import LLMProviderFactory


@pytest.mark.unit
def test_detect_provider_type_does_not_choose_deepseek_automatically() -> None:
    """Auto-detection must NOT pick DeepSeek, even when only its key is present.

    Gewijzigd 2026-10-19 (brief Mistral, ADR-041 B14): de automatische keuze draait over
    klantgegevens en DeepSeek (China, geen verwerkersovereenkomst) mag daar niet mee. Zonder
    sleutel van een toegestane provider valt het in tests op `mock` (nooit buiten tests).
    """
    config = {
        "deepseek_api_key": "deepseek-test-key",  # gitleaks:allow
        "google_api_key": "",
        "openai_api_key": "",
        "anthropic_api_key": "",
        "local_llm_url": "",
        "default_model": "gemini-1.5-flash",
        "llm_provider": "auto",
    }

    result = LLMProviderFactory._detect_provider_type(config)

    assert result != "deepseek"


@pytest.mark.unit
def test_detect_provider_type_ignores_explicit_deepseek_preference() -> None:
    """Een uitdrukkelijke keuze voor deepseek wordt NIET uitgevoerd, ook niet met sleutel (ADR-041 B14)."""
    config = {
        "deepseek_api_key": "deepseek-test-key",  # gitleaks:allow
        "google_api_key": "google-test-key",  # gitleaks:allow
        "openai_api_key": "",
        "anthropic_api_key": "",
        "local_llm_url": "",
        "default_model": "gemini-1.5-flash",
        "llm_provider": "deepseek",
    }

    result = LLMProviderFactory._detect_provider_type(config)

    assert result != "deepseek"
