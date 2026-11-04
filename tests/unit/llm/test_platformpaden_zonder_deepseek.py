"""DeepSeek is uit elk platformpad dat klantgegevens kan raken (brief 2026-10-19, ADR-041 B14).

Ook MET `DEEPSEEK_API_KEY` in de omgeving, en ook bij `LLM_PROVIDER=deepseek`. Een uitzondering is alleen
een klant die zijn EIGEN eindpunt opgeeft (dat is zijn keuze en zijn contract).

Daarnaast (regie, punt 2a): zonder `LLM_PROVIDER` en zonder sleutel valt `create_from_env` buiten tests
niet stil terug op een namaakmodel.
"""

from __future__ import annotations

import pytest

NEPSLEUTEL = "test-" + "mistral-" + "nepsleutel-0123456789"
DEEPSEEKSLEUTEL = "dk-" + "deepseek-nepsleutel-0123456789"


class TestCreateFromEnvKentGeenStilleMockStandaard:
    def test_zonder_provider_en_zonder_sleutel_is_het_buiten_tests_een_fout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.delenv("TESTING", raising=False)
        for naam in ("LLM_PROVIDER", "MISTRAL_API_KEY", "LLM_MODEL", "DEFAULT_LLM_MODEL"):
            monkeypatch.delenv(naam, raising=False)

        with pytest.raises(ValueError, match="LLM_PROVIDER"):
            ProviderFactory.create_from_env()

    def test_zonder_provider_maar_met_mistralsleutel_wordt_het_mistral(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.delenv("TESTING", raising=False)
        for naam in ("LLM_PROVIDER", "LLM_MODEL", "DEFAULT_LLM_MODEL", "LLM_API_KEY"):
            monkeypatch.delenv(naam, raising=False)
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        provider = ProviderFactory.create_from_env()

        assert provider.provider_name == "mistral"

    def test_in_tests_blijft_het_namaakmodel_de_standaard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.setenv("TESTING", "1")
        for naam in ("LLM_PROVIDER", "MISTRAL_API_KEY", "LLM_MODEL", "DEFAULT_LLM_MODEL"):
            monkeypatch.delenv(naam, raising=False)

        provider = ProviderFactory.create_from_env()

        assert provider.provider_name == "mock"

    def test_een_uitdrukkelijke_mockkeuze_werkt_ook_buiten_tests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

        provider = ProviderFactory.create_from_env()

        assert provider.provider_name == "mock"


class TestEenUitdrukkelijkeDeepseekkeuzeIsGeenToegangTotKlantgegevens:
    def test_deepseek_zonder_mistralsleutel_is_een_fout_en_geen_deepseekclient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
        monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEKSLEUTEL)
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

        with pytest.raises(ValueError, match="DeepSeek"):
            ProviderFactory.create_from_env()

    @pytest.mark.asyncio
    async def test_de_centrale_service_van_stapel_a_bouwt_nooit_een_deepseekprovider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.core.llm.llm_service as modul
        from src.core.llm.llm_client import LLMProvider

        monkeypatch.setattr(modul.LLMService, "_instance", None)
        monkeypatch.setattr(
            modul, "OllamaProvider", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("uit"))
        )
        for naam in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY"):
            monkeypatch.delenv(naam, raising=False)
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEKSLEUTEL)
        service = modul.LLMService()

        await service.initialize()

        assert LLMProvider.DEEPSEEK not in service.providers

    def test_de_automatische_keuze_van_stapel_a_kiest_geen_deepseek_zonder_mistralsleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.provider_factory import LLMProviderFactory

        monkeypatch.setenv("TESTING", "1")
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEKSLEUTEL)
        config = LLMProviderFactory._get_provider_config()
        config["llm_provider"] = "deepseek"

        assert LLMProviderFactory._detect_provider_type(config) != "deepseek"


class TestDeClientfabriekenBouwenGeenDeepseek:
    def test_de_clientfabriek_van_stapel_a_weigert_deepseek(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.llm_client import create_llm_client

        monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEKSLEUTEL)

        with pytest.raises(ValueError):
            create_llm_client("deepseek")

    def test_de_configfabriek_van_stapel_a_weigert_een_deepseekconfig(self) -> None:
        from src.core.llm.llm_client import (
            LLMConfig,
            LLMModel,
            LLMProvider,
            create_llm_client_from_config,
        )

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK,
            model=LLMModel.DEEPSEEK_CHAT,
            api_key=DEEPSEEKSLEUTEL,
        )

        with pytest.raises(ValueError):
            create_llm_client_from_config(config)

    def test_de_configfabriek_van_de_gedeelde_stapel_weigert_een_deepseekconfig(self) -> None:
        from src.core.shared.llm_client import (
            LLMConfig,
            LLMModel,
            LLMProvider,
            create_llm_client_from_config,
        )

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK,
            model=LLMModel.DEEPSEEK_CHAT,
            api_key=DEEPSEEKSLEUTEL,
        )

        with pytest.raises(ValueError):
            create_llm_client_from_config(config)

    def test_de_standaardconfig_kiest_geen_deepseek_ook_met_sleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm import llm_client
        from src.core.shared.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "deepseek_api_key", DEEPSEEKSLEUTEL, raising=False)

        assert llm_client.get_default_llm_config().provider != llm_client.LLMProvider.DEEPSEEK

    def test_de_cva_config_kiest_geen_deepseek_ook_met_sleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.shared.config import get_settings
        from src.core.shared.cva_llm_config import get_cva_llm_config
        from src.core.shared.llm_client import LLMProvider

        settings = get_settings()
        monkeypatch.setattr(settings, "deepseek_api_key", DEEPSEEKSLEUTEL, raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")

        assert get_cva_llm_config().provider != LLMProvider.DEEPSEEK


@pytest.mark.asyncio
class TestDeFallbackKetenRoeptDeepseekNooitAan:
    async def test_een_deepseekmodel_in_de_keten_wordt_geweigerd_zonder_netwerkverkeer(
        self,
    ) -> None:
        from src.core.llm.fallback_chain import LLMFallbackChain, ModelConfig, ModelTier

        keten = LLMFallbackChain()
        config = ModelConfig(name="deepseek-chat", tier=ModelTier.PRIMARY, provider="deepseek")

        with pytest.raises(ValueError, match="DeepSeek"):
            await keten._call_model(config, "hallo", None, None, 0.1, 10, 5.0)


class TestGate2Ronde1:
    """Gate 2 (security-reviewer, 2026-10-19): drie paden die de eerste ronde nog open liet."""

    def test_de_gegarandeerde_service_kent_deepseek_niet_meer_ook_met_sleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.llm_config import LLMConfig, LLMProviderType

        monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEKSLEUTEL)
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")

        keuze = LLMConfig().get_provider_priority()

        assert LLMProviderType.DEEPSEEK not in keuze

    def test_een_uitdrukkelijke_registrykeuze_voor_deepseek_wordt_geweigerd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.provider_factory import LLMProviderFactory

        monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEKSLEUTEL)
        LLMProviderFactory.reset()

        with pytest.raises(ValueError, match="verwerkersovereenkomst"):
            LLMProviderFactory.get_provider(provider_type="deepseek")

    def test_de_beoordelaarsconfiguratie_van_de_critic_kiest_geen_leveranciers_meer(self) -> None:
        import yaml

        from tests.architecture.test_geen_deepseek_voor_klantgegevens import REPO

        data = yaml.safe_load((REPO / "config/agents/critic_agent.yaml").read_text(encoding="utf-8"))

        assert "judge_provider_types" not in data

    def test_de_routeringstest_neemt_de_tenant_uit_de_jwt_en_niet_uit_de_querystring(self) -> None:
        import inspect

        from src.core.api.v1.agentic.router_debug import test_routing

        parameters = inspect.signature(test_routing).parameters

        assert ("tenant_id" in parameters, "current_user" in parameters) == (False, True)

    @pytest.mark.parametrize("naam", ["DeepSeek", "DEEPSEEK", " deepseek ", "Qwen"])
    def test_de_weigering_in_de_registry_let_niet_op_hoofdletters(self, naam: str) -> None:
        from src.core.llm.provider_factory import LLMProviderFactory

        LLMProviderFactory.reset()

        with pytest.raises(ValueError, match="verwerkersovereenkomst"):
            LLMProviderFactory.get_provider(provider_type=naam)
