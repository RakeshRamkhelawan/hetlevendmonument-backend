"""
Guard against silent MockProvider fallback in production.

Findings: LLM-MOCK-009
"""



import pytest

from src.core.services.llm.service import LLMService


@pytest.fixture(autouse=True)
def _geen_omgevingssleutel_van_een_taalmodel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deze tests gaan uit van een omgeving ZONDER `MISTRAL_API_KEY` en `LLM_PROVIDER`.

    Een eerdere test of een lokaal dotenv-bestand kan ze zetten (gemeten 2026-10-19 in een brede run:
    `LLM_PROVIDER=Mistral` en een sleutel aanwezig). Sinds `LLM_PROVIDER=deepseek` met een Mistralsleutel
    Mistral wordt, maakt dat een DeepSeek-testopzet stil anders.
    """
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


@pytest.mark.unit
def test_llm_service_raises_in_production_when_config_missing(monkeypatch) -> None:
    """Production + missing LLM config must fail hard, never fall back to mock."""
    monkeypatch.setattr(
        "src.core.services.llm.service.is_production",
        lambda: True,
    )

    # Force ProviderFactory.create_from_env to raise ValueError.
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises((RuntimeError, ValueError)):
        LLMService()


@pytest.mark.unit
def test_llm_service_allows_mock_fallback_outside_production(monkeypatch) -> None:
    """Outside production the existing mock fallback must remain available."""
    monkeypatch.setattr(
        "src.core.services.llm.service.is_production",
        lambda: False,
    )

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    service = LLMService()

    assert service.provider.provider_name == "mock"


@pytest.mark.unit
def test_llm_service_rejects_mock_provider_in_production(monkeypatch) -> None:
    """Even if provider creation succeeds, a mock provider in production is rejected."""
    monkeypatch.setattr(
        "src.core.services.llm.service.is_production",
        lambda: True,
    )

    # Explicitly request mock provider; the post-construction guard must still reject it.
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock-model")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(RuntimeError):
        LLMService()


# ---------------------------------------------------------------------------------
# Een provider die ANDERS HEET maar wel een namaakmodel bedient
#
# Gemeten 2026-09-21: de guard vroeg `self.provider.provider_name == "mock"`, en die naam
# wordt afgeleid van de KLASSENAAM (`base.py:200`,
# `self.__class__.__name__.replace("Provider", "").lower()`). Een samengestelde provider --
# de failoverketen van fase 2b -- heet daarmee "keten" en passeert de controle, ook als hij
# intern alleen het namaakmodel kan bereiken. Geen enkele test werd daar rood van.
#
# De guard vraagt sinds vandaag `serves_mock`. Deze twee tests houden dat vast: de eerste
# faalt zodra iemand teruggaat naar een naamsvergelijking, de tweede voorkomt dat het
# antwoord "weiger dan maar alles" wordt.
# ---------------------------------------------------------------------------------


class _KetenAchtigeProvider:
    """Een provider die NIET "mock" heet maar wel een namaakmodel bedient.

    Bewust geen echte `LLMProvider`-subklasse: die roept in `__init__` een configuratie-
    validatie aan en zou hier alleen ruis toevoegen. Wat de guard van een provider LEEST is
    `provider_name` en `serves_mock`, en dat is precies wat dit dubbel levert.
    """

    provider_name = "keten"
    serves_mock = True

    class config:  # kleine letter: alleen voor de logregel in LLMService.__init__
        model = "keten-model"


class _EchteProvider:
    """Dezelfde vorm, maar deze bedient geen namaakmodel.

    Bewust GEEN subklasse van het dubbel hierboven: dan verplaatst een wijziging aan het ene
    dubbel stil ook het andere, en verliezen de twee tests hun onafhankelijkheid.
    """

    provider_name = "deepseek"
    serves_mock = False

    class config:  # kleine letter: alleen voor de logregel in LLMService.__init__
        model = "deepseek-chat"


@pytest.mark.unit
def test_een_provider_die_anders_heet_maar_mock_bedient_wordt_geweigerd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """De naam van het buitenste object mag de controle niet bepalen."""
    monkeypatch.setattr("src.core.services.llm.service.is_production", lambda: True)
    monkeypatch.setattr(
        "src.core.services.llm.service.ProviderFactory.create_from_env",
        lambda **_: _KetenAchtigeProvider(),
    )

    with pytest.raises(RuntimeError):
        LLMService()


@pytest.mark.unit
def test_een_provider_die_GEEN_mock_bedient_mag_in_productie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """De tegenrichting. Zonder deze helft is "weiger alles" een geldige oplossing."""
    monkeypatch.setattr("src.core.services.llm.service.is_production", lambda: True)
    monkeypatch.setattr(
        "src.core.services.llm.service.ProviderFactory.create_from_env",
        lambda **_: _EchteProvider(),
    )

    service = LLMService()

    # De assertie die telt is dat de constructie hierboven NIET omviel; deze regel legt
    # vast dat de guard het juiste heeft gelezen en niet iets anders.
    assert service.provider.serves_mock is False


@pytest.mark.unit
def test_de_standaard_leidt_serves_mock_af_uit_de_naam() -> None:
    """Elke BESTAANDE provider moet zich onveranderd gedragen.

    Zonder deze test zou een verkeerde standaard in de basisklasse (bijvoorbeeld altijd
    `False`) elke echte provider door de guard laten -- inclusief het namaakmodel zelf.
    """
    from src.core.services.llm.factory import ProviderFactory

    mock_provider = ProviderFactory.create("mock", "mock-model")
    ollama_provider = ProviderFactory.create("ollama", "gemma4:e4b-it-qat")

    assert mock_provider.serves_mock is True
    assert ollama_provider.serves_mock is False


@pytest.mark.unit
def test_een_provider_ZONDER_serves_mock_laat_de_dienst_niet_starten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed als iemand een provider bouwt die de eigenschap helemaal mist.

    Een Gate 2-reviewer wees erop dat de twee dubbels hierboven het attribuut DRAGEN, en dus
    groen zouden blijven als de guard ooit `getattr(..., "serves_mock", False)` zou worden --
    precies de herschrijving die het gedrag omdraait van weigeren naar doorlaten. Deze test
    legt het huidige gedrag vast: ontbreekt de eigenschap, dan komt de dienst niet tot stand.
    """

    class _ZonderEigenschap:
        provider_name = "iets"

        class config:  # kleine letter: alleen voor de logregel in LLMService.__init__
            model = "iets"

    monkeypatch.setattr("src.core.services.llm.service.is_production", lambda: True)
    monkeypatch.setattr(
        "src.core.services.llm.service.ProviderFactory.create_from_env",
        lambda **_: _ZonderEigenschap(),
    )

    with pytest.raises(AttributeError):
        LLMService()


@pytest.mark.unit
def test_een_klant_die_zijn_eindpunt_mock_noemt_bedient_GEEN_namaakmodel() -> None:
    """Het label van de klant mag de productieguard niet sturen.

    Gemeten 2026-09-21 voordat `OpenAICompatibleProvider.serves_mock` bestond: met
    `provider_label='mock'` gaf de standaard `True` voor een ECHT klant-eindpunt, waarmee die
    klant zijn eigen productie-LLM stillegde met een `RuntimeError`. Sinds BE-LLM-003 komt dat
    label uit een vrij tekstveld van 64 tekens dat de klant zelf vult.
    """
    from src.core.services.llm.base import LLMConfig
    from src.core.services.llm.providers.openai_compatible import OpenAICompatibleProvider

    for label in ("mock", "MOCK", "  Mock  "):
        provider = OpenAICompatibleProvider(
            LLMConfig(
                model="llama3",
                base_url="https://echt.klant.example/v1",
                extra_params={"provider_label": label},
            )
        )
        assert provider.provider_name == "mock", "de naam mag het label gewoon volgen"
        assert provider.serves_mock is False, (
            f"label {label!r} maakte van een echt eindpunt een namaakmodel"
        )
