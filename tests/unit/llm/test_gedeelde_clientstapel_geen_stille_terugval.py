"""De gedeelde clientstapel valt nergens stil terug op een ander model (brief 2026-10-20, ADR-041 B14).

Gemeten op 8fdb38cb in `src/core/shared/llm_client.py`:
- `create_llm_client("anthropic")` gaf een GOOGLE-client (de configfabriek zei: "Anthropic not implemented -
  fallback to Google");
- `create_llm_client("google")` zonder sleutel viel door naar Google/Local/mock;
- een onbekende provider gaf een namaakclient;
- `create_llm_client("mock")` werkte ook buiten tests.
Een aanroeper die om model X vraagt, krijgt model X of een FOUT, nooit een ander model.
"""

from __future__ import annotations

import pytest

NEPSLEUTEL = "test-" + "google-" + "nepsleutel-0123456789"


@pytest.fixture
def zonder_sleutels(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    from src.core.shared.config import get_settings

    settings = get_settings()
    for veld in ("google_api_key", "anthropic_api_key", "deepseek_api_key", "openai_api_key"):
        monkeypatch.setattr(settings, veld, None, raising=False)
    return monkeypatch


class TestDeGedeeldeStapel:
    def test_anthropic_is_geen_stille_googleclient(
        self, zonder_sleutels: pytest.MonkeyPatch
    ) -> None:
        from src.core.shared.config import get_settings
        from src.core.shared.llm_client import create_llm_client

        zonder_sleutels.setattr(get_settings(), "anthropic_api_key", NEPSLEUTEL, raising=False)
        zonder_sleutels.setattr(get_settings(), "google_api_key", NEPSLEUTEL, raising=False)

        with pytest.raises(ValueError, match="anthropic"):
            create_llm_client("anthropic")

    def test_google_zonder_sleutel_valt_niet_door_naar_een_ander_model(
        self, zonder_sleutels: pytest.MonkeyPatch
    ) -> None:
        from src.core.shared.llm_client import create_llm_client

        with pytest.raises(ValueError, match="google"):
            create_llm_client("google")

    def test_een_onbekende_provider_is_een_fout_en_geen_namaakclient(
        self, zonder_sleutels: pytest.MonkeyPatch
    ) -> None:
        from src.core.shared.llm_client import create_llm_client

        with pytest.raises(ValueError, match="onbekend"):
            create_llm_client("een-leverancier-die-niet-bestaat")

    def test_mock_is_buiten_tests_een_fout(self, zonder_sleutels: pytest.MonkeyPatch) -> None:
        from src.core.shared.llm_client import create_llm_client

        zonder_sleutels.delenv("TESTING", raising=False)

        with pytest.raises(ValueError, match="namaak"):
            create_llm_client("mock")

    def test_mock_blijft_werken_in_tests(self, zonder_sleutels: pytest.MonkeyPatch) -> None:
        from src.core.shared.llm_client import MockLLMClient, create_llm_client

        zonder_sleutels.setenv("TESTING", "1")

        assert isinstance(create_llm_client("mock"), MockLLMClient)

    def test_de_configfabriek_maakt_van_anthropic_geen_google(self) -> None:
        from src.core.shared.llm_client import (
            LLMConfig,
            LLMModel,
            LLMProvider,
            create_llm_client_from_config,
        )

        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC, model=LLMModel.CLAUDE_3_5_SONNET, api_key=NEPSLEUTEL
        )

        with pytest.raises(ValueError, match="anthropic"):
            create_llm_client_from_config(config)

    def test_mock_via_de_configfabriek_is_buiten_tests_een_fout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.shared.llm_client import (
            LLMConfig,
            LLMModel,
            LLMProvider,
            create_llm_client_from_config,
        )

        monkeypatch.delenv("TESTING", raising=False)
        config = LLMConfig(provider=LLMProvider.MOCK, model=LLMModel.MOCK_MODEL, api_key="x")

        with pytest.raises(ValueError, match="namaak"):
            create_llm_client_from_config(config)


class TestDeStandaardconfigsVanStapelA:
    def test_zonder_enige_configuratie_is_er_buiten_tests_geen_mockconfig(
        self, zonder_sleutels: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm import llm_client
        from src.core.shared.config import get_settings

        zonder_sleutels.delenv("TESTING", raising=False)
        zonder_sleutels.setattr(get_settings(), "ollama_base_url", "", raising=False)

        with pytest.raises(ValueError, match="geen taalmodel"):
            llm_client.get_default_llm_config()
