"""COMP-006: CVAService audit trail (ADR-019 hash chain).

ADR-019 + GDPR Art. 6(1)(c): chat() en hard_delete_conversation() moeten een auditbaar
spoor achterlaten via best_effort.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCVAChatAuditTrail:
    """CVAService.chat() moet AuditLog entry aanmaken via best_effort."""

    @pytest.mark.asyncio
    async def test_chat_creates_audit_log_entry(self):
        """CVAService.chat() moet een AuditLogEmitEvent emitteren via governance_bus (SP-CVA-COMP-006)."""
        from src.core.services.cva_service import CVAService
        from src.core.shared.events.governance_events import AuditLogEmitEvent

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 99
        mock_conversation.title = None

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 12, "model": "gemini"})
        )

        mock_decision = MagicMock()
        mock_decision.decision_id = "test-decision-id"
        mock_council = MagicMock()

        emitted_events: list[object] = []

        async def capture_emit(event: object) -> int:
            emitted_events.append(event)
            return 1

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
            patch(
                "src.core.services.cva_service.governance_bus.emit",
                new=AsyncMock(side_effect=capture_emit),
            ),
        ):
            svc = CVAService(db_session=mock_db, llm_service=mock_llm)
            await svc.chat(message="Audit test", user_id=5, tenant_id=3)

        audit_events = [e for e in emitted_events if isinstance(e, AuditLogEmitEvent)]
        assert len(audit_events) >= 1, (
            "CVAService.chat() emitteerde geen AuditLogEmitEvent. "
            "Vereist voor ADR-019 audit trail (SP-CVA-COMP-006)."
        )

        cva_audit = next(
            e
            for e in audit_events
            if isinstance(e, AuditLogEmitEvent) and e.event_type == "cva_chat"
        )
        assert cva_audit.tenant_id == 3
        assert cva_audit.event_metadata.get("user_id") == 5

    @pytest.mark.asyncio
    async def test_chat_succeeds_even_when_audit_log_fails(self):
        """best_effort: audit log fout mag de chat response NIET blokkeren (SP-CVA-COMP-006)."""
        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        commit_calls = []

        async def failing_commit():
            if commit_calls:
                raise RuntimeError("audit db fout gesimuleerd")
            commit_calls.append(1)

        mock_db.commit = AsyncMock(side_effect=failing_commit)
        mock_db.rollback = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 77
        mock_conversation.title = "existing"

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(
            return_value=("Antwoord", {"total_tokens": 8, "model": "gemini"})
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
            result = await svc.chat(message="Best effort test", user_id=2, tenant_id=1)

        assert result["response"] == "Antwoord", (
            "CVAService.chat() faalde door audit log fout. "
            "best_effort moet audit fouten absorberen (SP-CVA-COMP-006)."
        )


class TestHardDeleteAuditTrail:
    """hard_delete_conversation() moet AuditLog aanmaken via best_effort (GDPR Art.17 + ADR-019)."""

    @pytest.mark.asyncio
    async def test_hard_delete_creates_audit_entry_with_required_fields(self):
        """hard_delete_conversation() emitteert AuditLogEmitEvent via governance_bus (ADR-019)."""
        from src.core.services.cva_service import CVAService
        from src.core.shared.events.governance_events import AuditLogEmitEvent

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 42

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        mock_db.delete = AsyncMock()

        emitted_events: list[object] = []

        async def capture_emit(event: object) -> int:
            emitted_events.append(event)
            return 1

        with patch(
            "src.core.services.cva_service.governance_bus.emit",
            new=AsyncMock(side_effect=capture_emit),
        ):
            svc = CVAService(db_session=mock_db, llm_service=MagicMock())
            await svc.hard_delete_conversation(conversation_id=42, user_id=7, tenant_id=2)

        audit_events = [e for e in emitted_events if isinstance(e, AuditLogEmitEvent)]
        assert len(audit_events) >= 1, (
            "hard_delete_conversation() emitteerde geen AuditLogEmitEvent (ADR-019)."
        )
        event = audit_events[0]
        assert event.event_type == "gdpr_erasure"
        assert event.threat_level == "info"
        assert event.client_ip == "service"
        assert event.endpoint is not None
        assert "42" in event.endpoint
        assert event.description is not None
        assert event.event_metadata is not None
        assert event.event_metadata.get("conversation_id") == 42
        assert event.tenant_id == 2
        assert event.event_metadata.get("user_id") == 7

    @pytest.mark.asyncio
    async def test_hard_delete_succeeds_even_when_audit_log_fails(self):
        """best_effort: audit log fout mag hard delete NIET blokkeren (GDPR Art.17)."""
        from src.core.services.cva_service import CVAService

        commit_calls = []

        async def first_commit_ok_then_fail():
            commit_calls.append(1)
            if len(commit_calls) > 1:
                raise RuntimeError("audit db fout gesimuleerd")

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock(side_effect=first_commit_ok_then_fail)
        mock_db.rollback = AsyncMock()

        mock_conversation = MagicMock()
        mock_conversation.id = 55

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_conversation
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        mock_db.delete = AsyncMock()

        svc = CVAService(db_session=mock_db, llm_service=MagicMock())

        # Deletion must NOT raise even if the audit commit fails
        await svc.hard_delete_conversation(conversation_id=55, user_id=3, tenant_id=1)

        # Primary delete commit was called (commit_calls[0])
        assert len(commit_calls) >= 1, "Primaire delete commit werd nooit aangeroepen."
