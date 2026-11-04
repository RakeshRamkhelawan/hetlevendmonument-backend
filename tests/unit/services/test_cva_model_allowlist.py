"""SEC-002: CVAService.chat() model override MOET een allowlist valideren.

Rode tests:
- Onbekend model wordt genegeerd (fallback naar default LLM)
- Willekeurige string mag niet ongevalideerd naar LLMService gaan
- Toegestaan model bereikt LLMService pas nadat allowlist controle plaatsvond
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


class TestCVAModelAllowlist:
    """CVAService.chat() model override MOET gevalideerd worden (SEC-002)."""

    @pytest.mark.asyncio
    async def test_unknown_model_override_is_rejected_and_uses_default(self):
        """Onbekend model-override wordt genegeerd -- fallback naar geconfigureerde LLM (SEC-002)."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_default_llm = MagicMock()
        mock_default_llm.provider = MagicMock()
        mock_default_llm.provider.provider_name = "gemini"
        mock_default_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
        )

        created_llm_services: list[object] = []

        def track_llm_init(model: object = None, **_kwargs: object) -> MagicMock:
            created_llm_services.append(model)
            svc = MagicMock()
            svc.provider = MagicMock()
            svc.provider.provider_name = "gemini"
            svc.generate = AsyncMock(
                return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
            )
            return svc

        mock_council = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision_id = "test-id"

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.core.services.cva_service.build_council",
                new_callable=AsyncMock,
                return_value=mock_council,
            ),
            patch(
                "src.core.services.cva_service.require_council_approval",
                new_callable=AsyncMock,
                return_value=mock_decision,
            ),
            patch("src.core.services.cva_service.LLMService", side_effect=track_llm_init),
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_default_llm)
            await svc.chat(
                message="Test",
                user_id=1,
                tenant_id=1,
                model="evil-model://inject",
            )

        # "evil-model://inject" must NOT have been passed to LLMService
        assert "evil-model://inject" not in created_llm_services, (
            "LLMService werd aangemaakt met onbekend model 'evil-model://inject'. "
            "SEC-002: model override MOET gevalideerd worden tegen een allowlist."
        )

    def test_the_user_model_override_list_is_gone(self):
        """Er is GEEN lijst van door de gebruiker te kiezen modellen meer (brief 2026-10-19, ADR-041 B14).

        De lijst bestond uit drie Gemini-modellen (Google, VS) en liet een verzoek de keuze van de klant
        (mistral of ollama) omzeilen. Het model volgt de tenant, niet het verzoek.
        """
        source = (_REPO_ROOT / "src/core/services/cva_service.py").read_text(encoding="utf-8")
        assert "_ALLOWED_CVA_MODELS" not in source

    @pytest.mark.asyncio
    async def test_invalid_model_does_not_reach_llm_service_constructor(self):
        """Ongeldig model bereikt de LLMService constructor NOOIT -- blocked door allowlist (SEC-002).

        Rode test: ROOD totdat allowlist-check VOOR de LLMService constructor staat.
        Verschil met test_unknown_model_override_is_rejected: hier faalt LLMService NIET --
        het model wordt geblokkeerd VOORDAT LLMService wordt aangeroepen.
        """
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        llm_constructor_called_with: list[object] = []

        def track_and_succeed(model: object = None, **_kwargs: object) -> MagicMock:
            # This mock does NOT raise -- any rejection must come from allowlist before this call
            llm_constructor_called_with.append(model)
            svc = MagicMock()
            svc.provider = MagicMock()
            svc.provider.provider_name = "gemini"
            svc.generate = AsyncMock(
                return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
            )
            return svc

        mock_council = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision_id = "test-id"
        mock_default_llm = MagicMock()
        mock_default_llm.provider = MagicMock()
        mock_default_llm.provider.provider_name = "gemini"
        mock_default_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
        )

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.core.services.cva_service.build_council",
                new_callable=AsyncMock,
                return_value=mock_council,
            ),
            patch(
                "src.core.services.cva_service.require_council_approval",
                new_callable=AsyncMock,
                return_value=mock_decision,
            ),
            patch("src.core.services.cva_service.LLMService", side_effect=track_and_succeed),
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_default_llm)
            await svc.chat(
                message="Test",
                user_id=1,
                tenant_id=1,
                model="evil-model://inject",
            )

        assert "evil-model://inject" not in llm_constructor_called_with, (
            "LLMService constructor werd aangeroepen met 'evil-model://inject' ondanks niet-falende mock. "
            "SEC-002: allowlist-check moet VOOR de LLMService constructor plaatsvinden."
        )

    @pytest.mark.asyncio
    async def test_a_former_allowlist_model_is_ignored_and_the_tenant_model_is_used(self):
        """Ook een model dat vroeger op de lijst stond kiest NIETS meer: de tenantdienst antwoordt."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        created_with_model: list[object] = []

        def track_llm_init(model: object = None, **_kwargs: object) -> MagicMock:
            created_with_model.append(model)
            svc = MagicMock()
            svc.provider = MagicMock()
            svc.provider.provider_name = "gemini"
            svc.generate = AsyncMock(
                return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
            )
            return svc

        mock_council = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision_id = "test-id"

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.core.services.cva_service.build_council",
                new_callable=AsyncMock,
                return_value=mock_council,
            ),
            patch(
                "src.core.services.cva_service.require_council_approval",
                new_callable=AsyncMock,
                return_value=mock_decision,
            ),
            patch("src.core.services.cva_service.LLMService", side_effect=track_llm_init),
        ):
            default_llm = MagicMock()
            default_llm.provider = MagicMock()
            default_llm.provider.provider_name = "mistral"
            default_llm.generate = AsyncMock(
                return_value=("Antwoord", {"total_tokens": 5, "model": "mistral"})
            )
            svc = CVAService(db_session=mock_db, llm_service=default_llm)
            await svc.chat(
                message="Test",
                user_id=1,
                tenant_id=1,
                model="gemini-2.5-flash",
            )

        assert (created_with_model, default_llm.generate.await_count) == ([], 1)
