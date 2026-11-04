"""ARCH-003+011+BE-001: delete_conversation() MOET een audit event emitteren via governance_bus."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCVASoftDeleteAuditTrail:
    """delete_conversation() emitteert governance_bus AuditLogEmitEvent (ADR-019)."""

    @pytest.mark.asyncio
    async def test_delete_conversation_emits_audit_event(self):
        """delete_conversation() MOET AuditLogEmitEvent emitteren via governance_bus (ARCH-003)."""
        from src.core.services.cva_service import CVAService
        from src.core.shared.events.governance_events import AuditLogEmitEvent

        mock_conv = MagicMock()
        mock_conv.id = 10
        mock_conv.is_active = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        emitted: list[object] = []

        async def capture(event: object) -> int:
            emitted.append(event)
            return 1

        svc = CVAService(db_session=mock_db)
        with patch(
            "src.core.services.cva_service.governance_bus.emit",
            new=AsyncMock(side_effect=capture),
        ):
            await svc.delete_conversation(conversation_id=10, user_id=1, tenant_id=1)

        audit_events = [e for e in emitted if isinstance(e, AuditLogEmitEvent)]
        assert len(audit_events) >= 1, (
            "delete_conversation() emitteerde geen AuditLogEmitEvent. "
            "ARCH-003+011: voeg best_effort governance_bus.emit toe na soft delete commit."
        )
        event = audit_events[0]
        assert event.event_type == "cva_conversation_deleted", (
            f"event_type is '{event.event_type}', verwacht 'cva_conversation_deleted' (ARCH-003)."
        )

    @pytest.mark.asyncio
    async def test_delete_conversation_audit_failure_does_not_block_delete(self):
        """Audit fout bij soft-delete mag de delete NIET blokkeren (best_effort, ARCH-011)."""
        from src.core.services.cva_service import CVAService

        mock_conv = MagicMock()
        mock_conv.id = 11
        mock_conv.is_active = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        failing_emit = AsyncMock(side_effect=RuntimeError("DB unavailable gesimuleerd"))

        svc = CVAService(db_session=mock_db)
        with patch(
            "src.core.services.cva_service.governance_bus.emit",
            new=failing_emit,
        ):
            # Must NOT raise -- best_effort absorbs audit failures
            await svc.delete_conversation(conversation_id=11, user_id=1, tenant_id=1)

        # Audit must have been ATTEMPTED (absorbed by best_effort, not silently skipped)
        assert failing_emit.call_count >= 1, (
            "governance_bus.emit werd nooit aangeroepen -- audit trail ontbreekt volledig. "
            "ARCH-011: audit moet geprobeerd worden en via best_effort geabsorbeerd, niet weggelaten."
        )
        # Soft delete should have been applied regardless
        assert mock_conv.is_active is False, (
            "Soft delete werd niet uitgevoerd ondanks audit fout. "
            "ARCH-011: audit fout mag delete NIET blokkeren."
        )
