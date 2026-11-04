"""AIACT-003: CVAService.chat() en chat_stream() MOETEN council gate doorlopen.

Tests zijn ROOD totdat AIACT-003 fix is geimplementeerd.
Patch-paden zijn op cva_service module (niet governance_gate module).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import GovernanceVetoError


class TestCVACouncilGate:
    """CVAService moet require_council_approval aanroepen VOOR LLM generate."""

    @pytest.mark.asyncio
    async def test_chat_calls_require_council_approval(self):
        """CVAService.chat() roept require_council_approval() aan (AIACT-003)."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
        )

        mock_decision = MagicMock()
        mock_decision.decision_id = "test-decision-id-001"
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
            ) as mock_gate,
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            response = await svc.chat(message="Hallo", user_id=1, tenant_id=1)

        mock_gate.assert_called_once()
        assert response["response"] == "Antwoord"

    @pytest.mark.asyncio
    async def test_chat_vetoed_by_council_blocks_llm(self):
        """CVA chat propageert GovernanceVetoError als council veto geeft; LLM mag niet worden aangeroepen."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=("Antwoord", {}))
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
                side_effect=GovernanceVetoError(
                    message="Hoog risico gedetecteerd",
                    decision_id="test-decision-id",
                    verdict="BLOCKED",
                ),
            ),
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            with pytest.raises(GovernanceVetoError) as exc_info:
                await svc.chat(message="Gevaarlijk bericht", user_id=1, tenant_id=1)

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "GOVERNANCE_BLOCKED"
        mock_llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_response_contains_decision_id(self):
        """ChatResponse bevat decision_id van council deliberation (AIACT-002 + AIACT-003)."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 5, "model": "gemini"})
        )

        mock_decision = MagicMock()
        mock_decision.decision_id = "council-decision-abc123"
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
            response = await svc.chat(message="Test", user_id=1, tenant_id=1)

        assert response.get("decision_id") == "council-decision-abc123", (
            "ChatResponse moet decision_id bevatten voor Right-to-Explanation (AIACT-002)."
        )

    @pytest.mark.asyncio
    async def test_chat_stream_vetoed_propagates_governance_veto_error(self):
        """CVAService.chat_stream() propageert GovernanceVetoError -- streaming mag niet starten (AIACT-003)."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        mock_llm = MagicMock()
        mock_llm.stream_generate = AsyncMock()
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
                side_effect=GovernanceVetoError(
                    message="Stream geblokkeerd door governance",
                    decision_id="stream-veto-decision-id",
                    verdict="BLOCKED",
                ),
            ),
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            with pytest.raises(GovernanceVetoError) as exc_info:
                async for _ in svc.chat_stream(message="Test stream", user_id=1, tenant_id=1):
                    pass

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "GOVERNANCE_BLOCKED"
        mock_llm.stream_generate.assert_not_called()
