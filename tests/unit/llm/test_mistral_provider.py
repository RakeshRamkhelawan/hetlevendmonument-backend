"""Mistral (EU) als taalmodel, per klant te kiezen; DeepSeek en mock nooit stil voor klantgegevens.

Brief: docs/agent-briefs/generated/2026-10-15-sprint-dag-mistral-als-eu-taalmodel.md (ADR-041 B14).

Gemeten vooraf (9c58df3d): de fabriek (`provider_factory`) kende geen `mistral`; de terugvalketen
(`get_fallback_chain`) registreerde DeepSeek zodra `DEEPSEEK_API_KEY` bestond, en een tenantverzoek had
geen manier om een model te weigeren; de centrale `LLMService.initialize` zette DeepSeek bovenaan.

Alleen de HTTP-laag is een dubbel (`httpx.MockTransport`) met een antwoord in de vorm van Mistral;
de provider, de fabriek, de registry en de ketenregel zijn echt. De sleutel in deze tests is een
verzonnen waarde, nooit een echte.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from src.core.llm.fallback_chain import LLMFallbackChain, ModelConfig, ModelTier
from src.core.llm.llm_client import LLMMessage
from src.core.llm.provider_factory import LLMProviderFactory
from src.core.llm.provider_registry import ProviderRegistry

#: Verzonnen, herkenbaar als nep; de test zoekt hem terug in logregels en in de weergave.
NEPSLEUTEL = "test-" + "mistral-" + "nepsleutel-0123456789"


def _antwoord(inhoud: str = "ok", **bericht: object) -> dict[str, object]:
    return {
        "id": "cmpl-1",
        "model": "mistral-small-latest",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": inhoud, **bericht},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


class _Server:
    """Een nep-Mistral: bewaart de verzoeken en geeft een vast antwoord."""

    def __init__(self, antwoord: dict[str, object] | None = None, status: int = 200) -> None:
        self.verzoeken: list[httpx.Request] = []
        self._antwoord = antwoord if antwoord is not None else _antwoord()
        self._status = status

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.verzoeken.append(request)
            return httpx.Response(self._status, json=self._antwoord)

        return httpx.MockTransport(handler)

    def lichaam(self) -> dict[str, object]:
        return json.loads(self.verzoeken[-1].content)


def _provider(server: _Server, sleutel: str | None = NEPSLEUTEL):  # type: ignore[no-untyped-def]
    from src.core.llm.mistral_provider import MistralProvider

    return MistralProvider(api_key=sleutel, transport=server.transport())


@pytest.fixture(autouse=True)
def _schone_omgeving(monkeypatch: pytest.MonkeyPatch) -> None:
    for naam in ("MISTRAL_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(naam, raising=False)
    LLMProviderFactory.reset()
    import src.core.llm.fallback_chain as keten

    monkeypatch.setattr(keten, "_default_chain", None)


# --- de fabriek kent mistral en vraagt de sleutel -------------------------------------------


class TestDeFabriekKentMistral:
    def test_de_registry_vindt_provider_mistral(self) -> None:
        assert ProviderRegistry.get("mistral") is not None

    def test_de_sleutel_komt_uit_de_omgeving_variabele_MISTRAL_API_KEY(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        config = LLMProviderFactory._get_provider_config()

        assert LLMProviderFactory._get_api_key_for_provider("mistral", config) == NEPSLEUTEL

    def test_zonder_sleutel_kiest_de_automatische_keuze_geen_mistral(self) -> None:
        config = LLMProviderFactory._get_provider_config()
        config["llm_provider"] = "mistral"

        assert LLMProviderFactory._detect_provider_type(config) != "mistral"

    def test_met_sleutel_kiest_de_automatische_keuze_mistral_voor_alle_andere(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)
        monkeypatch.setenv("GOOGLE_API_KEY", "y" * 20)

        config = LLMProviderFactory._get_provider_config()

        assert LLMProviderFactory._detect_provider_type(config) == "mistral"

    def test_de_automatische_keuze_kiest_nooit_deepseek(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)

        config = LLMProviderFactory._get_provider_config()

        assert LLMProviderFactory._detect_provider_type(config) != "deepseek"

    def test_get_provider_geeft_een_mistral_provider_met_de_sleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        provider = LLMProviderFactory.get_provider("mistral")

        assert type(provider).__name__ == "MistralProvider"

    def test_een_onbekende_provider_valt_buiten_tests_niet_stil_terug_op_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TESTING", raising=False)

        with pytest.raises(RuntimeError, match="niet teruggevallen op een namaakmodel"):
            LLMProviderFactory.get_provider("bestaat-niet")


# --- de provider zelf: JSON-uitvoer, toolaanroep, geen sleutel in logs ----------------------


@pytest.mark.asyncio
class TestDeProviderPraatMistral:
    async def test_het_verzoek_gaat_naar_het_eu_eindpunt_met_de_sleutel_als_bearer(self) -> None:
        server = _Server()
        provider = _provider(server)

        await provider.chat_completion([LLMMessage(role="user", content="hallo")])

        verzoek = server.verzoeken[-1]
        assert (str(verzoek.url), verzoek.headers["authorization"]) == (
            "https://api.mistral.ai/v1/chat/completions",
            f"Bearer {NEPSLEUTEL}",
        )

    async def test_het_antwoord_wordt_gelezen(self) -> None:
        provider = _provider(_Server(_antwoord("hoi")))

        antwoord = await provider.chat_completion([LLMMessage(role="user", content="hallo")])

        assert (antwoord.success, antwoord.content, antwoord.provider) == (True, "hoi", "mistral")

    async def test_json_uitvoer_vraagt_response_format_json_object(self) -> None:
        server = _Server(_antwoord('{"a": 1}'))
        provider = _provider(server)

        await provider.complete_json([LLMMessage(role="user", content="geef json")], dict)

        assert server.lichaam()["response_format"] == {"type": "json_object"}

    async def test_een_toolaanroep_in_mistralvorm_wordt_goed_gelezen(self) -> None:
        oproep = {
            "id": "abc123",
            "type": "function",
            "function": {"name": "zoek_factuur", "arguments": '{"nummer": "F-1"}'},
        }
        provider = _provider(_Server(_antwoord("", tool_calls=[oproep])))

        antwoord = await provider.generate_response(
            "",
            messages=[{"role": "user", "content": "zoek F-1"}],
            tools=[
                {
                    "name": "zoek_factuur",
                    "description": "zoek een factuur",
                    "parameters": {"type": "object", "properties": {"nummer": {"type": "string"}}},
                }
            ],
        )

        assert (antwoord["success"], antwoord["function_calls"]) == (
            True,
            [{"name": "zoek_factuur", "args": {"nummer": "F-1"}}],
        )

    async def test_de_tools_gaan_in_openai_vorm_naar_mistral(self) -> None:
        server = _Server()
        provider = _provider(server)

        await provider.generate_response(
            "",
            messages=[{"role": "user", "content": "x"}],
            tools=[{"name": "t", "description": "d", "parameters": {"type": "object"}}],
        )

        assert server.lichaam()["tools"] == [
            {
                "type": "function",
                "function": {"name": "t", "description": "d", "parameters": {"type": "object"}},
            }
        ]

    async def test_zonder_sleutel_is_het_antwoord_een_duidelijke_fout_en_gaat_er_niets_uit(
        self,
    ) -> None:
        server = _Server()
        provider = _provider(server, sleutel=None)

        antwoord = await provider.chat_completion([LLMMessage(role="user", content="hallo")])

        assert (
            antwoord.success,
            "MISTRAL_API_KEY" in (antwoord.error_message or ""),
            server.verzoeken,
        ) == (False, True, [])

    async def test_een_afwijzing_van_mistral_staat_niet_met_de_sleutel_in_het_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        server = _Server({"message": f"Unauthorized {NEPSLEUTEL}"}, status=401)
        provider = _provider(server)

        with caplog.at_level(logging.DEBUG):
            await provider.chat_completion([LLMMessage(role="user", content="hallo")])

        assert NEPSLEUTEL not in caplog.text

    async def test_de_sleutel_staat_niet_in_de_foutmelding_van_een_afwijzing(self) -> None:
        server = _Server({"message": f"Unauthorized {NEPSLEUTEL}"}, status=401)
        provider = _provider(server)

        antwoord = await provider.chat_completion([LLMMessage(role="user", content="hallo")])

        assert NEPSLEUTEL not in (antwoord.error_message or "")

    async def test_de_sleutel_staat_niet_in_de_weergave_van_de_provider(self) -> None:
        provider = _provider(_Server())

        assert NEPSLEUTEL not in f"{provider!r} {provider!s}"

    async def test_het_model_komt_uit_LLM_MODEL_als_de_provider_mistral_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "mistral")
        monkeypatch.setenv("LLM_MODEL", "mistral-large-latest")
        server = _Server()
        provider = _provider(server)

        await provider.chat_completion([LLMMessage(role="user", content="x")])

        assert server.lichaam()["model"] == "mistral-large-latest"

    async def test_een_deepseek_model_in_LLM_MODEL_wordt_voor_mistral_genegeerd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De CD zet nog `LLM_MODEL=deepseek-chat`; dat mag niet bij Mistral aankomen."""
        monkeypatch.setenv("LLM_PROVIDER", "mistral")
        monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
        server = _Server()
        provider = _provider(server)

        await provider.chat_completion([LLMMessage(role="user", content="x")])

        assert server.lichaam()["model"] == "mistral-small-latest"


# --- de terugvalketen: nooit DeepSeek voor een tenant, nooit stil van ollama naar gehuurd ---


def _model(naam: str, provider: str, tier: ModelTier = ModelTier.PRIMARY) -> ModelConfig:
    return ModelConfig(name=naam, tier=tier, provider=provider)


class _Opnemer:
    """Vervangt `_call_model`: bewaart welke providers zijn aangeroepen en laat gekozen falen."""

    def __init__(self, faalt: set[str]) -> None:
        self.aangeroepen: list[str] = []
        self._faalt = faalt

    async def __call__(self, *, model_config: ModelConfig, **_rest: object) -> str:
        self.aangeroepen.append(model_config.provider)
        if model_config.provider in self._faalt:
            raise RuntimeError(f"{model_config.provider} is uitgevallen")
        return f"antwoord van {model_config.provider}"


def _keten(opnemer: _Opnemer, *modellen: ModelConfig) -> LLMFallbackChain:
    keten = LLMFallbackChain(max_fallbacks=10)
    for model in modellen:
        keten.register_model(model)
    keten._call_model = opnemer  # type: ignore[method-assign]
    return keten


@pytest.mark.asyncio
class TestDeTerugvalketenKentDeTenantkeuze:
    async def test_een_tenant_met_keuze_ollama_krijgt_bij_een_storing_geen_gehuurd_model(
        self,
    ) -> None:
        opnemer = _Opnemer(faalt={"ollama"})
        keten = _keten(
            opnemer,
            _model("mistral-small-latest", "mistral"),
            _model("llama3.2", "ollama", ModelTier.LOCAL),
        )

        resultaat = await keten.generate("hoi", tenant_keuze="ollama")

        assert (resultaat.success, opnemer.aangeroepen) == (False, ["ollama"])

    async def test_de_weigering_voor_ollama_is_een_zichtbare_fout_in_het_resultaat(self) -> None:
        opnemer = _Opnemer(faalt={"ollama"})
        keten = _keten(opnemer, _model("mistral-small-latest", "mistral"))

        resultaat = await keten.generate("hoi", tenant_keuze="ollama")

        assert any("ollama" in fout for fout in resultaat.errors)

    async def test_voor_een_tenantverzoek_wordt_deepseek_nooit_gekozen(self) -> None:
        opnemer = _Opnemer(faalt={"mistral", "ollama"})
        keten = _keten(
            opnemer,
            _model("mistral-small-latest", "mistral"),
            _model("deepseek-chat", "deepseek"),
            _model("llama3.2", "ollama", ModelTier.LOCAL),
        )

        await keten.generate("hoi", tenant_keuze="mistral")

        assert "deepseek" not in opnemer.aangeroepen

    async def test_voor_een_tenantverzoek_wordt_ook_een_ander_gehuurd_model_niet_gekozen(
        self,
    ) -> None:
        opnemer = _Opnemer(faalt={"mistral"})
        keten = _keten(
            opnemer,
            _model("mistral-small-latest", "mistral"),
            _model("gpt-3.5-turbo", "openai"),
            _model("gemini-2.5-pro", "google"),
        )

        resultaat = await keten.generate("hoi", tenant_keuze="mistral")

        assert (resultaat.success, opnemer.aangeroepen) == (False, ["mistral"])

    async def test_mistral_valt_bij_een_storing_door_naar_het_eigen_model(self) -> None:
        opnemer = _Opnemer(faalt={"mistral"})
        keten = _keten(
            opnemer,
            _model("mistral-small-latest", "mistral"),
            _model("llama3.2", "ollama", ModelTier.LOCAL),
        )

        resultaat = await keten.generate("hoi", tenant_keuze="mistral")

        assert (resultaat.success, opnemer.aangeroepen) == (True, ["mistral", "ollama"])

    async def test_een_onbekende_tenantkeuze_wordt_geweigerd_en_niet_stil_standaard(self) -> None:
        opnemer = _Opnemer(faalt=set())
        keten = _keten(opnemer, _model("mistral-small-latest", "mistral"))

        resultaat = await keten.generate("hoi", tenant_keuze="deepseek")

        assert (resultaat.success, opnemer.aangeroepen, resultaat.errors) == (
            False,
            [],
            ["Onbekende taalmodelkeuze 'deepseek'; het verzoek is niet verstuurd"],
        )


class TestDeStandaardketenRegistreertDeepseekNiet:
    def test_de_standaardketen_registreert_mistral_als_de_sleutel_er_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.fallback_chain import get_fallback_chain

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        keten = get_fallback_chain()

        assert "mistral" in {m.provider for lijst in keten._models.values() for m in lijst}

    def test_de_standaardketen_registreert_deepseek_niet_ook_niet_met_een_sleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.fallback_chain import get_fallback_chain

        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)

        keten = get_fallback_chain()

        assert "deepseek" not in {m.provider for lijst in keten._models.values() for m in lijst}


# --- het proefscript: zonder sleutel verstuurt het niets en toont het nooit een sleutel ----------


def _proefscript():  # type: ignore[no-untyped-def]
    import importlib.util
    from pathlib import Path

    pad = Path(__file__).resolve().parents[3] / "scripts" / "proef_mistral.py"
    spec = importlib.util.spec_from_file_location("proef_mistral_onder_test", pad)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestHetProefscript:
    def test_zonder_sleutel_meldt_het_niet_gemeten_en_stopt_met_exitcode_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
    ) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        module = _proefscript()

        code = module.main(["--root", str(tmp_path)])

        assert (code, "niet gemeten" in capsys.readouterr().out) == (2, True)

    def test_met_sleutel_toont_het_script_de_waarde_niet(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
    ) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        module = _proefscript()

        async def zonder_netwerk() -> int:
            return 0

        monkeypatch.setattr(module, "proef", zonder_netwerk)

        code = module.main(["--root", str(tmp_path)])

        assert (code, NEPSLEUTEL in capsys.readouterr().out) == (0, False)


# --- de centrale LLMService (stapel A): Mistral eerst, DeepSeek alleen uitdrukkelijk, geen stille mock ---


@pytest.fixture
def verse_service(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Een nieuwe `LLMService` zonder echte netwerkproviders (Ollama uit, geen Google/Anthropic)."""
    import src.core.llm.llm_service as modul

    monkeypatch.setattr(modul.LLMService, "_instance", None)
    monkeypatch.setattr(
        modul, "OllamaProvider", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("uit"))
    )
    for naam in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(naam, raising=False)
    return modul.LLMService


@pytest.mark.asyncio
class TestDeCentraleServiceKiestMistral:
    async def test_met_een_mistralsleutel_is_mistral_de_standaard(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.llm.llm_client import LLMProvider

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        service = verse_service()

        await service.initialize()

        assert service.default_provider == LLMProvider.MISTRAL

    async def test_een_deepseeksleutel_alleen_maakt_deepseek_niet_actief(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.llm.llm_client import LLMProvider

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)
        service = verse_service()

        await service.initialize()

        assert LLMProvider.DEEPSEEK not in service.providers

    async def test_deepseek_blijft_uit_ook_als_de_uitrol_er_uitdrukkelijk_voor_kiest(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.llm.llm_client import LLMProvider

        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        service = verse_service()

        await service.initialize()

        assert LLMProvider.DEEPSEEK not in service.providers

    async def test_zonder_enige_provider_is_er_buiten_tests_geen_namaakmodel(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("TESTING", raising=False)
        service = verse_service()

        await service.initialize()

        assert service.providers == {}

    async def test_zonder_enige_provider_is_er_in_tests_wel_een_namaakmodel(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.llm.llm_client import LLMProvider

        monkeypatch.setenv("TESTING", "1")
        service = verse_service()

        await service.initialize()

        assert LLMProvider.MOCK in service.providers

    async def test_een_aanroep_zonder_provider_geeft_een_duidelijke_fout_en_geen_verzonnen_antwoord(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("TESTING", raising=False)
        service = verse_service()
        await service.initialize()

        antwoord = await service.generate_response("hallo")

        assert antwoord["success"] is False


# --- Gate 2 ronde 1: https verplicht, tool-argumenten gedetokeniseerd, Mistral eerst in de keten -----


class TestDeSleutelGaatAlleenNaarEenBeveiligdAdres:
    def test_een_http_adres_voor_mistral_wordt_geweigerd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.mistral_provider import MistralProvider

        monkeypatch.setenv("MISTRAL_BASE_URL", "http://mistral.example.test/v1")

        with pytest.raises(ValueError, match="https"):
            MistralProvider(api_key=NEPSLEUTEL)

    def test_een_http_adres_voor_mistral_wordt_in_stapel_b_geweigerd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.base import LLMConfig
        from src.core.services.llm.providers.mistral import MistralProvider as StapelB

        monkeypatch.setenv("MISTRAL_BASE_URL", "http://mistral.example.test/v1")

        with pytest.raises(ValueError, match="https"):
            StapelB(LLMConfig(model="mistral-small-latest", api_key=NEPSLEUTEL))


@pytest.mark.asyncio
class TestToolargumentenKrijgenHunPersoonsgegevensTerug:
    async def test_een_gemaskeerde_waarde_in_de_argumenten_wordt_hersteld(self) -> None:
        # De gebruiker noemt een e-mailadres; het model krijgt een token en roept de tool met dat
        # token aan. De tool moet het ECHTE adres krijgen.
        server = _Server()
        provider = _provider(server)

        berichten = [{"role": "user", "content": "zoek de klant jan@voorbeeld.nl"}]
        _gemaskeerd, tokens = provider._gdpr_enforcer.redact_pii(berichten[0]["content"])
        token = next(iter(tokens))
        oproep = {
            "id": "c1",
            "type": "function",
            "function": {"name": "zoek_klant", "arguments": json.dumps({"email": token})},
        }
        server._antwoord = _antwoord("", tool_calls=[oproep])

        antwoord = await provider.generate_response(
            "", messages=berichten, tools=[{"name": "zoek_klant", "parameters": {"type": "object"}}]
        )

        assert antwoord["function_calls"] == [
            {"name": "zoek_klant", "args": {"email": "jan@voorbeeld.nl"}}
        ]


class TestMistralStaatVoorDeAndereGehuurdeModellenInDeKeten:
    def test_mistral_wordt_als_eerste_geprobeerd_ook_met_een_googlesleutel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.llm.fallback_chain import ModelTier, get_fallback_chain

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        monkeypatch.setenv("GOOGLE_API_KEY", "g" * 20)
        monkeypatch.setenv("OPENAI_API_KEY", "o" * 20)

        keten = get_fallback_chain()

        assert keten._models[ModelTier.PRIMARY][0].provider == "mistral"


class TestEenDeepseekUitrolWordtMistralZodraDeSleutelErIs:
    """Gate 2 ronde 2: de CD zet nog `LLM_PROVIDER=deepseek`. Staat `MISTRAL_API_KEY` er, dan krijgen
    platform-aanroepers (cva, workflowbouwer, crag, ...) toch Mistral, zonder dat de CD eerst hoeft te wijzigen."""

    def test_create_from_env_kiest_mistral_met_de_sleutel_van_mistral(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
        monkeypatch.setenv("LLM_API_KEY", "dk-" + "deepseek-nepsleutel-0123456789")
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        provider = ProviderFactory.create_from_env()

        assert (
            provider.provider_name,
            provider.config.model,
            provider.config.api_key,
            provider.config.base_url,
        ) == ("mistral", "mistral-small-latest", NEPSLEUTEL, "https://api.mistral.ai/v1")

    def test_zonder_mistralsleutel_is_een_uitdrukkelijke_deepseekkeuze_een_fout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory

        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
        monkeypatch.setenv("LLM_API_KEY", "dk-" + "deepseek-nepsleutel-0123456789")

        with pytest.raises(ValueError, match="DeepSeek"):
            ProviderFactory.create_from_env()

    def test_de_automatische_keuze_van_stapel_a_wordt_mistral(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)
        config = LLMProviderFactory._get_provider_config()
        config["llm_provider"] = "deepseek"

        assert LLMProviderFactory._detect_provider_type(config) == "mistral"

    @pytest.mark.asyncio
    async def test_de_centrale_service_van_stapel_a_laat_deepseek_dan_uit(
        self, verse_service, monkeypatch: pytest.MonkeyPatch
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.llm.llm_client import LLMProvider

        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        service = verse_service()

        await service.initialize()

        assert (LLMProvider.DEEPSEEK in service.providers, service.default_provider) == (
            False,
            LLMProvider.MISTRAL,
        )


class TestEenOnbruikbareProviderWordtBuitenTestsGeenStilNamaakmodel:
    """Gate 2 (gerichte review op ff48c72d): `LLMService.__init__` maakte buiten productie bij een
    ValueError een MockProvider met alleen een gewone waarschuwing; staging valt daaronder."""

    def test_zonder_testomgeving_is_een_ontbrekende_sleutel_een_fout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

        with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
            LLMService(provider="mistral", model="mistral-small-latest")

    def test_in_tests_blijft_het_namaakmodel_mogelijk_met_een_zichtbare_melding(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.setenv("TESTING", "1")
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

        with caplog.at_level(logging.WARNING):
            dienst = LLMService(provider="mistral", model="mistral-small-latest")

        assert (dienst.provider.provider_name, "[MOCK]" in caplog.text) == ("mock", True)

    def test_een_uitdrukkelijke_mockkeuze_blijft_werken_buiten_tests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.delenv("TESTING", raising=False)

        dienst = LLMService(provider="mock", model="mock-model")

        assert dienst.provider.provider_name == "mock"


class TestDeConfigurekentDeSleutelNietInDeWeergave:
    def test_de_providerconfiguratie_toont_de_sleutel_niet_in_repr(self) -> None:
        from src.core.config.production_config import LLMProviderConfig

        config = LLMProviderConfig(name="mistral", api_key=NEPSLEUTEL)

        assert NEPSLEUTEL not in repr(config) + str(config)


class TestDeDevComposeGeeftDeMistralsleutelNietAlsAlgemeneLLMSleutel:
    def test_er_staat_geen_LLM_API_KEY_in_de_omgeving_van_de_dev_compose(self) -> None:
        from pathlib import Path

        import yaml

        pad = Path(__file__).resolve().parents[3] / "docker-compose.dev.yml"
        compose = yaml.safe_load(pad.read_text(encoding="utf-8"))
        omgeving = [
            str(regel)
            for dienst in compose.get("services", {}).values()
            for regel in (dienst.get("environment") or [])
        ]

        assert not [regel for regel in omgeving if regel.startswith("LLM_API_KEY")]


class TestDeCvaLaatGeenModelKeuzeVanHetVerzoekToe:
    def test_een_modelkeuze_van_het_verzoek_bestaat_niet_meer_dus_ook_geen_deepseek(self) -> None:
        import src.core.services.cva_service as cva_service

        assert not hasattr(cva_service, "_ALLOWED_CVA_MODELS")
