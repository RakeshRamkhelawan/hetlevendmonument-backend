"""
Failover chain wiring for the Copilot LLM handler.

Findings: LLM-ADR26-002
"""

import pytest

from src.core.llm.fallback_chain import ModelTier, get_fallback_chain
from src.core.llm.provider_factory import LLMProviderFactory


@pytest.mark.unit
def test_copilot_builds_no_provider_fallback_from_the_environment(monkeypatch) -> None:
    """De copilot bouwt GEEN eigen terugval op `LLM_FALLBACK_PROVIDER` meer.

    Gewijzigd 2026-10-19 (brief geen DeepSeek, ADR-041 B14): die terugval stuurde klantgegevens naar een
    tweede leverancier die de klant niet koos. De copilot gebruikt het model van de tenant
    (`TenantTaalmodel`); uitval binnen de keuze van de klant regelt `LLMService.for_tenant`.
    """
    import src.core.copilot.dependencies as dependencies

    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "gemini")

    assert not hasattr(dependencies, "_build_fallback_providers")


@pytest.mark.unit
def test_fallback_chain_registers_deepseek_never_by_default(monkeypatch) -> None:
    """The app-wide fallback chain must NOT register DeepSeek, even with a key present.

    Gewijzigd 2026-10-19 (brief Mistral, ADR-041 B14): de keten verwerkt promptteksten uit
    klanttaken, en DeepSeek (China, geen verwerkersovereenkomst) mag daar niet mee. Mistral (EU) is
    het gehuurde standaardmodel; zie `tests/unit/llm/test_mistral_provider.py`.
    """
    import src.core.llm.fallback_chain as fallback_chain_module

    original_chain = fallback_chain_module._default_chain
    try:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")  # gitleaks:allow
        fallback_chain_module._default_chain = None

        chain = get_fallback_chain()

        registered_models = [
            model.name for tier_models in chain._models.values() for model in tier_models
        ]

        assert "deepseek-chat" not in registered_models
        assert "deepseek-reasoner" not in registered_models
        assert chain._models[ModelTier.PRIMARY] == [] or all(
            model.provider != "deepseek" for model in chain._models[ModelTier.PRIMARY]
        )
    finally:
        fallback_chain_module._default_chain = original_chain
        LLMProviderFactory.reset()
