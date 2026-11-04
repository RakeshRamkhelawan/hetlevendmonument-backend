"""De ene deur naar het taalmodel voor tenantverzoeken (brief 2026-10-19, ADR-041 B14).

`TenantTaalmodel` is de enige plek waar een dienst of agent die tenantgegevens verwerkt zijn taalmodel
vandaan haalt: de keuze van de klant via `LLMService.for_tenant`. Hij geeft de vormen terug die de
bestaande aanroepers al lezen (`generate_response` als woordenboek, `chat_completion` met `.content`),
zodat zij geen eigen client met een eigen leverancier meer hoeven te bouwen.

Wat een aanroeper NOOIT mag zien: een succesantwoord van een ander model dan het gekozen model.
"""

from __future__ import annotations

import pytest

from src.core.services.llm.base import LLMMessage, LLMServiceError

NEPSLEUTEL = "test-" + "mistral-" + "nepsleutel-0123456789"


class _NepDienst:
    """Een `LLMService`-dubbel: bewaart wat er gevraagd is en geeft een vast antwoord of een fout."""

    def __init__(self, antwoord: str = "ok", fout: Exception | None = None) -> None:
        self.berichten: list[list[LLMMessage]] = []
        self._antwoord = antwoord
        self._fout = fout
        self.provider = type(
            "P", (), {"provider_name": "mistral", "config": type("C", (), {"model": "m"})()}
        )()

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_rest: object,
    ) -> str:
        """`LLMService.generate` geeft de TEKST terug (zonder `return_usage`)."""
        self.berichten.append(messages)
        if self._fout is not None:
            raise self._fout
        return self._antwoord


@pytest.fixture
def for_tenant_dubbel(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Vervangt `LLMService.for_tenant` en onthoudt voor welke tenant hij werd opgevraagd."""
    from src.core.services.llm.service import LLMService

    opgevraagd: list[int] = []
    dienst = _NepDienst()

    async def nep(tenant_id: int) -> _NepDienst:
        opgevraagd.append(tenant_id)
        return dienst

    monkeypatch.setattr(LLMService, "for_tenant", staticmethod(nep))
    return opgevraagd, dienst


@pytest.mark.asyncio
class TestDeDeurGaatViaDeKeuzeVanDeKlant:
    async def test_het_model_wordt_opgevraagd_voor_de_tenant_van_het_verzoek(
        self, for_tenant_dubbel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        opgevraagd, _dienst = for_tenant_dubbel

        await TenantTaalmodel(7).generate_response("hallo")

        assert opgevraagd == [7]

    async def test_het_model_wordt_maar_een_keer_per_deur_opgevraagd(
        self, for_tenant_dubbel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        opgevraagd, _dienst = for_tenant_dubbel
        deur = TenantTaalmodel(7)

        await deur.generate_response("een")
        await deur.generate_response("twee")

        assert opgevraagd == [7]

    async def test_generate_response_geeft_het_woordenboek_dat_de_aanroepers_lezen(
        self, for_tenant_dubbel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        antwoord = await TenantTaalmodel(7).generate_response("hallo")

        assert (
            antwoord["success"],
            antwoord["content"],
            antwoord["text"],
            antwoord["provider"],
        ) == (True, "ok", "ok", "mistral")

    async def test_chat_completion_geeft_een_object_met_content_en_success(
        self, for_tenant_dubbel
    ) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        _opgevraagd, dienst = for_tenant_dubbel

        antwoord = await TenantTaalmodel(7).chat_completion(
            [type("M", (), {"role": "user", "content": "hoi"})()]
        )

        assert (antwoord.content, antwoord.success, dienst.berichten[0][0].content) == (
            "ok",
            True,
            "hoi",
        )

    async def test_een_systeemprompt_gaat_als_eigen_bericht_mee(self, for_tenant_dubbel) -> None:  # type: ignore[no-untyped-def]
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        _opgevraagd, dienst = for_tenant_dubbel

        await TenantTaalmodel(7).tekst("antwoord kort", systeem="je bent een router")

        assert [(m.role, m.content) for m in dienst.berichten[0]] == [
            ("system", "je bent een router"),
            ("user", "antwoord kort"),
        ]


@pytest.mark.asyncio
class TestEenStoringIsEenFoutEnGeenAnderModel:
    async def test_generate_response_meldt_een_storing_als_mislukt_en_niet_als_succes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        dienst = _NepDienst(fout=LLMServiceError("Mistral gaf HTTP 503"))

        async def nep(tenant_id: int) -> _NepDienst:
            return dienst

        monkeypatch.setattr(LLMService, "for_tenant", staticmethod(nep))

        antwoord = await TenantTaalmodel(7).generate_response("hallo")

        # Alleen het TYPE van de fout gaat naar de aanroeper; de tekst (met adres of melding) staat in het log.
        assert (antwoord["success"], antwoord["error"]) == (False, "LLMServiceError")

    async def test_tekst_laat_de_storing_door_aan_de_aanroeper(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        dienst = _NepDienst(fout=LLMServiceError("stuk"))

        async def nep(tenant_id: int) -> _NepDienst:
            return dienst

        monkeypatch.setattr(LLMService, "for_tenant", staticmethod(nep))

        with pytest.raises(LLMServiceError):
            await TenantTaalmodel(7).tekst("hallo")

    async def test_een_ongeldige_tenantkeuze_gaat_als_fout_door(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService
        from src.core.services.llm.tenant_deur import TenantTaalmodel
        from src.core.shared.tenant_llm_keuze import OnbekendeLLMKeuzeError

        async def nep(tenant_id: int) -> _NepDienst:
            raise OnbekendeLLMKeuzeError("deepseek")

        monkeypatch.setattr(LLMService, "for_tenant", staticmethod(nep))

        with pytest.raises(OnbekendeLLMKeuzeError):
            await TenantTaalmodel(7).tekst("hallo")


@pytest.mark.asyncio
class TestZonderTenantIsDeStandaardMistral:
    async def test_zonder_tenant_wordt_het_eu_standaardmodel_gebouwd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        for naam in ("LLM_PROVIDER", "LLM_MODEL", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(naam, raising=False)
        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        dienst = await TenantTaalmodel(None)._dienst()

        assert dienst.provider.provider_name == "mistral"

    async def test_zonder_tenant_en_zonder_sleutel_is_het_een_duidelijke_fout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.tenant_deur import TenantTaalmodel
        from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

        with pytest.raises(TenantLLMNietBeschikbaarError):
            await TenantTaalmodel(None)._dienst()
