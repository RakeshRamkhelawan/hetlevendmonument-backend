"""De taalmodelkeuze per klant: standaard Mistral, Ollama als tweede, nooit DeepSeek of mock.

Brief: docs/agent-briefs/generated/2026-10-15-sprint-dag-mistral-als-eu-taalmodel.md.

De keuze staat in `tenants.settings["llm_provider"]` (bestaande JSON-kolom, geen migratie). Deze tests
dekken de regel zelf (`src/core/llm/tenant_llm_keuze.py`) en het pad dat hem gebruikt
(`LLMService.for_tenant` van stapel B, waar de agenten per tenant hun taalmodel vandaan halen).

Wat vooraf gemeten is (9c58df3d): een tenant zonder eigen eindpunt kreeg via `for_tenant` de
PLATFORMSTANDAARD uit de omgeving (`LLM_PROVIDER`), en dat is op staging en productie DeepSeek.
"""

from __future__ import annotations

import pytest

from src.core.shared.tenant_llm_keuze import (
    STANDAARD_KEUZE,
    OnbekendeLLMKeuzeError,
    keuze_uit_instellingen,
    provider_mag_voor_keuze,
)

NEPSLEUTEL = "test-" + "mistral-" + "nepsleutel-0123456789"


class TestDeKeuzeUitDeTenantinstellingen:
    def test_zonder_instelling_is_de_keuze_mistral(self) -> None:
        assert keuze_uit_instellingen({}) == "mistral"

    def test_de_standaard_is_mistral(self) -> None:
        assert STANDAARD_KEUZE == "mistral"

    def test_geen_instellingen_is_ook_mistral(self) -> None:
        assert keuze_uit_instellingen(None) == "mistral"

    def test_ollama_is_de_tweede_keuze(self) -> None:
        assert keuze_uit_instellingen({"llm_provider": "ollama"}) == "ollama"

    def test_hoofdletters_en_spaties_worden_genormaliseerd(self) -> None:
        assert keuze_uit_instellingen({"llm_provider": " Ollama "}) == "ollama"

    @pytest.mark.parametrize("waarde", ["deepseek", "mock", "openai", "google", "", "onzin"])
    def test_een_andere_waarde_wordt_geweigerd_en_valt_niet_stil_terug_op_de_standaard(
        self, waarde: str
    ) -> None:
        with pytest.raises(OnbekendeLLMKeuzeError):
            keuze_uit_instellingen({"llm_provider": waarde})


class TestWelkeProviderBijWelkeKeuzeMag:
    @pytest.mark.parametrize(
        ("keuze", "provider", "toegestaan"),
        [
            ("mistral", "mistral", True),
            ("mistral", "ollama", True),
            ("mistral", "lmstudio", True),
            ("mistral", "deepseek", False),
            ("mistral", "mock", False),
            ("mistral", "openai", False),
            ("mistral", "google", False),
            ("ollama", "ollama", True),
            ("ollama", "lmstudio", True),
            ("ollama", "mistral", False),
            ("ollama", "deepseek", False),
            ("ollama", "mock", False),
        ],
    )
    def test_de_tabel(self, keuze: str, provider: str, toegestaan: bool) -> None:
        assert provider_mag_voor_keuze(provider, keuze) is toegestaan

    def test_een_onbekende_keuze_laat_niets_toe(self) -> None:
        assert provider_mag_voor_keuze("mistral", "deepseek") is False


# --- `LLMService.for_tenant`: de platformstandaard is niet langer DeepSeek ------------------


class _NepSessie:
    async def __aenter__(self) -> _NepSessie:
        return self

    async def __aexit__(self, *_uitzondering: object) -> None:
        return None


class _Keuzes:
    def __init__(self) -> None:
        self.instellingen: dict[str, object] = {}
        self.leesfout: Exception | None = None


class _LegeDienst:
    """De tenant-LLM-dienst voor een tenant zonder eigen rijen; de instellingen zijn instelbaar."""

    def __init__(self, keuzes: _Keuzes) -> None:
        self._keuzes = keuzes

    async def opgeslagen_rijen(self, tenant_id: int) -> list[object]:
        return []

    async def instellingen_van_de_klant(self, tenant_id: int) -> dict[str, object]:
        if self._keuzes.leesfout is not None:
            raise self._keuzes.leesfout
        return self._keuzes.instellingen

    async def beproef(self, tenant_id: int, rijen: list[object]) -> list[object]:
        return []


@pytest.fixture
def zonder_eigen_eindpunt(monkeypatch: pytest.MonkeyPatch) -> _Keuzes:
    """Een tenant zonder eigen rijen; de gekozen waarde in `tenants.settings` is instelbaar."""
    import src.core.database.session as sessie_module
    from src.core.services import tenant_llm_provider_service as tlps

    for naam in ("MISTRAL_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(naam, raising=False)
    keuzes = _Keuzes()
    monkeypatch.setattr(tlps, "bouw_tenant_llm_service", lambda db: _LegeDienst(keuzes))
    monkeypatch.setattr(sessie_module, "get_db_session", lambda: _NepSessie())
    return keuzes


@pytest.mark.asyncio
class TestForTenantKiestHetEuModel:
    async def test_een_tenant_zonder_keuze_krijgt_mistral(
        self, zonder_eigen_eindpunt: _Keuzes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)

        dienst = await LLMService.for_tenant(7)

        assert dienst.provider.provider_name == "mistral"

    async def test_een_platformstandaard_deepseek_in_de_omgeving_bereikt_de_tenant_niet(
        self, zonder_eigen_eindpunt: _Keuzes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "x" * 20)

        dienst = await LLMService.for_tenant(7)

        assert (dienst.provider.provider_name, dienst.provider.config.model) == (
            "mistral",
            "mistral-small-latest",
        )

    async def test_een_tenant_die_ollama_koos_krijgt_ollama(
        self, zonder_eigen_eindpunt: _Keuzes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        zonder_eigen_eindpunt.instellingen = {"llm_provider": "ollama"}

        dienst = await LLMService.for_tenant(7)

        assert dienst.provider.provider_name == "ollama"

    async def test_een_tenant_die_ollama_koos_bouwt_geen_gehuurd_model_als_terugval(
        self, zonder_eigen_eindpunt: _Keuzes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.factory import ProviderFactory
        from src.core.services.llm.service import LLMService

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        zonder_eigen_eindpunt.instellingen = {"llm_provider": "ollama"}
        gebouwd: list[str] = []
        echte_create = ProviderFactory.create.__func__  # type: ignore[attr-defined]

        def spion(cls: type[ProviderFactory], provider: str, *a: object, **k: object) -> object:
            gebouwd.append(provider)
            return echte_create(cls, provider, *a, **k)

        monkeypatch.setattr(ProviderFactory, "create", classmethod(spion))

        await LLMService.for_tenant(7)

        assert gebouwd == ["ollama"]

    async def test_mistral_zonder_sleutel_is_een_duidelijke_fout_en_geen_mock(
        self, zonder_eigen_eindpunt: _Keuzes
    ) -> None:
        from src.core.services.llm.service import LLMService

        with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
            await LLMService.for_tenant(7)

    async def test_een_niet_te_lezen_keuze_is_een_duidelijke_fout_en_geen_gehuurd_model(
        self, zonder_eigen_eindpunt: _Keuzes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService
        from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        zonder_eigen_eindpunt.leesfout = ConnectionError("database weg")

        with pytest.raises(TenantLLMNietBeschikbaarError):
            await LLMService.for_tenant(7)

    async def test_een_ongeldige_keuze_in_de_instellingen_is_een_fout(
        self, zonder_eigen_eindpunt: _Keuzes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.services.llm.service import LLMService

        monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
        zonder_eigen_eindpunt.instellingen = {"llm_provider": "deepseek"}

        with pytest.raises(OnbekendeLLMKeuzeError):
            await LLMService.for_tenant(7)


# --- de keuze wordt bij het OPSLAAN al gecontroleerd, niet pas bij het eerste verzoek -----------


class TestDeTenantschemasWeigerenEenVerbodenKeuze:
    def _create(self, **settings: object):  # type: ignore[no-untyped-def]
        from src.core.schemas.tenant_schemas import TenantCreate

        return TenantCreate(name="Klant", slug="klant-een", settings=dict(settings))

    def test_een_nieuwe_tenant_met_deepseek_wordt_geweigerd(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self._create(llm_provider="deepseek")

    def test_een_nieuwe_tenant_met_ollama_is_goed(self) -> None:
        assert self._create(llm_provider="ollama").settings["llm_provider"] == "ollama"

    def test_een_nieuwe_tenant_zonder_keuze_is_goed(self) -> None:
        assert "llm_provider" not in self._create().settings

    def test_een_wijziging_naar_mock_wordt_geweigerd(self) -> None:
        from pydantic import ValidationError

        from src.core.schemas.tenant_schemas import TenantUpdate

        with pytest.raises(ValidationError):
            TenantUpdate(settings={"llm_provider": "mock"})

    def test_een_wijziging_naar_mistral_is_goed(self) -> None:
        from src.core.schemas.tenant_schemas import TenantUpdate

        assert TenantUpdate(settings={"llm_provider": "mistral"}).settings == {
            "llm_provider": "mistral"
        }

    def test_andere_instellingen_blijven_onaangeroerd(self) -> None:
        from src.core.schemas.tenant_schemas import TenantUpdate

        assert TenantUpdate(settings={"four_eyes": True}).settings == {"four_eyes": True}


# --- Gate 2 ronde 1 (security-reviewer): de keuze mag niet stil verdwijnen of worden omzeild --------


@pytest.mark.asyncio
class TestDeAgentdeurValtNietStilTerugOpHetPlatformmodel:
    """`BaseSpecialistAgent._get_llm_service`: een fout in de TAALMODELKEUZE van de klant gaat door.

    Gemeten door de reviewer: de brede `except Exception` ving de bewuste fouten van
    `for_tenant` en bouwde `LLMService()`, de platformstandaard (DeepSeek in de uitrol)."""

    @staticmethod
    def _agent() -> object:
        from types import SimpleNamespace

        return SimpleNamespace(llm=None, tenant_id=7)

    async def _vraag(self, monkeypatch: pytest.MonkeyPatch, fout: Exception) -> object:
        from src.core.als.agents.specialist_base import BaseSpecialistAgent
        from src.core.services.llm.service import LLMService

        async def kapot(tenant_id: int) -> object:
            raise fout

        monkeypatch.setattr(LLMService, "for_tenant", staticmethod(kapot))
        return await BaseSpecialistAgent._get_llm_service(self._agent())  # type: ignore[arg-type]

    async def test_een_ongeldige_keuze_gaat_door_en_wordt_geen_platformmodel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(OnbekendeLLMKeuzeError):
            await self._vraag(monkeypatch, OnbekendeLLMKeuzeError("deepseek"))

    async def test_een_ontbrekende_sleutel_gaat_door(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

        with pytest.raises(TenantLLMNietBeschikbaarError):
            await self._vraag(monkeypatch, TenantLLMNietBeschikbaarError("MISTRAL_API_KEY"))

    async def test_een_ander_probleem_in_de_keten_van_de_klant_valt_ook_niet_terug_op_het_platformmodel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate 2 ronde 2: ook een databasestoring mag geen stille DeepSeek-taak opleveren."""
        from src.core.als.agents.specialist_base import BaseSpecialistAgent
        from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

        gebouwd: list[str] = []

        class _Platform:
            @staticmethod
            async def for_tenant(tenant_id: int) -> object:
                raise ConnectionError("database weg")

            def __new__(cls) -> object:  # type: ignore[misc]
                gebouwd.append("platformmodel")
                return "platformmodel"

        monkeypatch.setattr("src.core.als.agents.specialist_base.LLMService", _Platform)

        with pytest.raises(TenantLLMNietBeschikbaarError):
            await BaseSpecialistAgent._get_llm_service(self._agent())  # type: ignore[arg-type]

        assert gebouwd == []


class TestDeKeuzeVerdwijntNietBijEenWijziging:
    def test_een_nieuwe_settings_zonder_keuze_behoudt_de_oude_keuze(self) -> None:
        from src.core.shared.tenant_llm_keuze import behoud_llm_keuze

        assert behoud_llm_keuze({"llm_provider": "ollama", "a": 1}, {"b": 2}) == {
            "b": 2,
            "llm_provider": "ollama",
        }

    def test_een_uitdrukkelijk_nieuwe_keuze_wint(self) -> None:
        from src.core.shared.tenant_llm_keuze import behoud_llm_keuze

        assert behoud_llm_keuze({"llm_provider": "ollama"}, {"llm_provider": "mistral"}) == {
            "llm_provider": "mistral"
        }

    def test_zonder_oude_keuze_blijft_de_nieuwe_ongewijzigd(self) -> None:
        from src.core.shared.tenant_llm_keuze import behoud_llm_keuze

        assert behoud_llm_keuze({"a": 1}, {"b": 2}) == {"b": 2}

    def test_de_fout_bij_een_ongeldige_keuze_kapt_de_ruwe_waarde_af(self) -> None:
        with pytest.raises(OnbekendeLLMKeuzeError) as fout:
            keuze_uit_instellingen({"llm_provider": "x" * 500})

        assert len(str(fout.value)) < 200


@pytest.mark.asyncio
class TestUpdateTenantBehoudtDeKeuze:
    async def test_een_update_van_alleen_andere_instellingen_laat_ollama_staan(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from src.core.schemas.tenant_schemas import TenantUpdate
        from src.core.services.tenant_service import TenantService

        tenant = SimpleNamespace(
            id=7,
            settings={"llm_provider": "ollama"},
            domain=None,
            updated_at=None,
        )
        resultaat = MagicMock()
        resultaat.scalar_one_or_none.return_value = tenant
        db = MagicMock()
        db.execute = AsyncMock(return_value=resultaat)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        context = SimpleNamespace(bypass_filter=True, require_tenant=lambda: 7)
        dienst = TenantService(db, context)  # type: ignore[arg-type]

        try:
            await dienst.update_tenant(7, TenantUpdate(settings={"four_eyes": True}))
        except Exception:  # de antwoordvorm doet er niet toe, alleen wat er is opgeslagen
            pass

        assert tenant.settings == {"four_eyes": True, "llm_provider": "ollama"}
