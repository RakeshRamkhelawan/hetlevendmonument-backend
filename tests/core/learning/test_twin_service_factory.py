"""
Unit tests voor twin_service_factory LLM chain building.

Controleert:
- EU-only chain bevat alleen Local + Mock (geen cloud providers)
- Global chain bevat cloud providers + Local + Mock
- _is_eu_only_tenant detecteert 'eu-only' correct
- _is_eu_only_tenant is fail-safe bij DB errors
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.services.twin_service_factory import (
    _build_provider_chain,
    _is_eu_only_tenant,
)


class TestBuildProviderChain:
    """Tests voor _build_provider_chain: het taalmodel is de keuze van de TENANT (brief 2026-10-20)."""

    CLOUDSLEUTELS = {
        "ANTHROPIC_API_KEY": "sk-ant-api03-valid-key-long-enough",
        "GOOGLE_API_KEY": "AIzaSyvalid-key-long-enough",
        "OLLAMA_BASE_URL": "http://localhost:11434",
    }

    def test_de_keten_is_het_model_van_de_tenant_ook_met_cloudsleutels(self):
        with patch.dict("os.environ", self.CLOUDSLEUTELS, clear=True):
            chain = _build_provider_chain(7, eu_only=False)

        names = [type(p).__name__ for p in chain]
        assert names == ["TenantSuggestionProvider"]

    def test_eu_only_verandert_de_keten_niet(self):
        with patch.dict("os.environ", self.CLOUDSLEUTELS, clear=True):
            chain = _build_provider_chain(7, eu_only=True)

        assert [type(p).__name__ for p in chain] == ["TenantSuggestionProvider"]

    def test_zonder_enige_sleutel_is_er_geen_stille_mock(self):
        with patch.dict("os.environ", {}, clear=True):
            chain = _build_provider_chain(7, eu_only=False)

        assert [type(p).__name__ for p in chain] == ["TenantSuggestionProvider"]

    def test_een_uitdrukkelijke_mockkeuze_geeft_alleen_de_mock(self):
        with patch.dict("os.environ", {"LLM_PROVIDER": "mock"}, clear=True):
            chain = _build_provider_chain(7, eu_only=False)

        assert [type(p).__name__ for p in chain] == ["MockSuggestionProvider"]

    def test_soft_cap_laat_een_betaald_model_vallen_voor_de_vaste_tekst(self):
        with patch.dict("os.environ", self.CLOUDSLEUTELS, clear=True):
            chain = _build_provider_chain(7, budget_status="soft_cap", tenant_keuze="mistral")

        assert [type(p).__name__ for p in chain] == ["MockSuggestionProvider"]

    def test_soft_cap_houdt_een_eigen_model_van_de_tenant(self):
        with patch.dict("os.environ", self.CLOUDSLEUTELS, clear=True):
            chain = _build_provider_chain(7, budget_status="soft_cap", tenant_keuze="ollama")

        assert [type(p).__name__ for p in chain] == ["TenantSuggestionProvider"]

    def test_hard_cap_returns_mock_only(self):
        with patch.dict("os.environ", self.CLOUDSLEUTELS, clear=True):
            chain = _build_provider_chain(7, eu_only=False, budget_status="hard_cap")

        assert [type(p).__name__ for p in chain] == ["MockSuggestionProvider"]

    def test_hard_cap_overrides_eu_only(self):
        """Hard cap takes precedence over EU-only (most restrictive)."""
        with patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://localhost:11434"}):
            chain = _build_provider_chain(7, eu_only=True, budget_status="hard_cap")

        assert [type(p).__name__ for p in chain] == ["MockSuggestionProvider"]


@pytest.mark.asyncio
class TestIsEuOnlyTenant:
    """Tests voor _is_eu_only_tenant."""

    async def test_returns_true_for_eu_only_residency(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = "eu-only"
        db.execute = AsyncMock(return_value=result_mock)

        assert await _is_eu_only_tenant(db, tenant_id=1) is True

    async def test_returns_false_for_global_residency(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = "global"
        db.execute = AsyncMock(return_value=result_mock)

        assert await _is_eu_only_tenant(db, tenant_id=1) is False

    async def test_returns_false_when_tenant_not_found(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        assert await _is_eu_only_tenant(db, tenant_id=999) is False

    async def test_returns_true_on_db_error(self):
        """Fail-secure: kan de residency niet worden vastgesteld, dan EU-only aannemen.

        Deze test eiste tot 2026-07-31 het omgekeerde ("assume global (not EU-only)") en
        dus `False`. Dat is de onveilige kant: wie bij een DB-fout aanneemt dat een tenant
        GEEN EU-only-residency heeft, riskeert dat EU-data buiten de EU verwerkt wordt.
        `_is_eu_only_tenant` kiest expliciet de strengste aanname
        ("Fail-secure: cannot verify residency -> protect eu-only data"). De test liep
        achter op die correctie (gevonden OP-11).
        """
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        assert await _is_eu_only_tenant(db, tenant_id=1) is True
