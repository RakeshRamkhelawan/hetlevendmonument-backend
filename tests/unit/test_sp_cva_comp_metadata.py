"""COMP-001: CVAService.chat() moet personalization_consent_status in metadata retourneren.

GDPR Art. 6 -- frontend moet weten of geheugen-features actief zijn op basis van consent.
Test is ROOD totdat Fix A is geimplementeerd.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCVAChatConsentMetadata:
    """CVAService.chat() moet personalization_consent_status opnemen in metadata."""

    @pytest.mark.asyncio
    async def test_chat_metadata_contains_personalization_consent_status(self):
        """chat() metadata moet 'personalization_consent_status' bevatten (SP-CVA-COMP-001)."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 42
        mock_conversation.title = None

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord van assistent", {"total_tokens": 10, "model": "gemini"})
        )

        mock_decision = MagicMock()
        mock_decision.decision_id = "test-decision-id"
        mock_council = MagicMock()

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
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            result = await svc.chat(
                message="Hallo",
                user_id=1,
                tenant_id=1,
            )

        assert "personalization_consent_status" in result.get("metadata", {}), (
            "CVAService.chat() metadata mist 'personalization_consent_status'. "
            "Vereist voor GDPR Art. 6 + frontend consent banner (SP-CVA-COMP-001)."
        )

    @pytest.mark.asyncio
    async def test_chat_metadata_consent_status_granted_when_consent_given(self):
        """personalization_consent_status == 'granted' als user consent heeft."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 42
        mock_conversation.title = None

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
        )

        mock_decision = MagicMock()
        mock_decision.decision_id = "test-decision-id"
        mock_council = MagicMock()

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
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            result = await svc.chat(message="Test", user_id=1, tenant_id=1)

        assert result["metadata"]["personalization_consent_status"] == "granted"

    @pytest.mark.asyncio
    async def test_chat_metadata_consent_status_required_when_no_consent(self):
        """personalization_consent_status == 'required' als user geen consent heeft."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 42
        mock_conversation.title = None

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
        )

        mock_decision = MagicMock()
        mock_decision.decision_id = "test-decision-id"
        mock_council = MagicMock()

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=False,
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
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            result = await svc.chat(message="Test", user_id=1, tenant_id=1)

        assert result["metadata"]["personalization_consent_status"] == "required"
