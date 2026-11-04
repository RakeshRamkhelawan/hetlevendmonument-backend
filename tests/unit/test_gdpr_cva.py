"""GDPR compliance tests for CVA data.

Ref: CVA Audit Phase 4 - GDPR Compliance
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGDPRCVAExport:
    """GDPR data export must include CVA conversations."""

    @pytest.mark.asyncio
    async def test_export_includes_cva_conversations(self):
        """User data export must contain a 'cva_conversations' key."""
        # This test verifies the collect_user_data function in privacy router
        # includes CVA conversations in the export
        from src.core.api.v1.privacy.router import collect_user_data

        # Mock user
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.tenant_id = 1

        # Mock session
        mock_session = AsyncMock()

        # Mock conversation data
        mock_conversations = [
            MagicMock(
                id=1,
                title="Test Conversation",
                created_at="2026-01-01T00:00:00",
                is_active=True,
            )
        ]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_conversations
        mock_session.execute.return_value = mock_result

        # Call collect_user_data
        data = await collect_user_data(mock_session, mock_user)

        # Verify cva_conversations key exists
        assert "cva_conversations" in data, (
            "GDPR export missing 'cva_conversations'. "
            "CVA conversation data must be included in user data export."
        )


class TestHardDeleteConversation:
    """GDPR right-to-erasure requires actual data deletion."""

    @pytest.mark.asyncio
    async def test_hard_delete_conversation_exists(self):
        """CVAService must have hard_delete_conversation method."""
        from src.core.services.cva_service import CVAService

        assert hasattr(CVAService, "hard_delete_conversation"), (
            "CVAService missing hard_delete_conversation method. "
            "Required for GDPR Article 17 (Right to Erasure)."
        )

    @pytest.mark.asyncio
    async def test_hard_delete_deletes_messages_and_conversation(self):
        """hard_delete_conversation must DELETE messages then conversation."""
        from src.core.services.cva_service import CVAService

        # Mock conversation
        mock_conv = MagicMock()
        mock_conv.id = 1

        # Mock service
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        service = CVAService(db_session=mock_db, llm_service=AsyncMock())
        service._get_conversation = AsyncMock(return_value=mock_conv)

        # Call hard_delete
        await service.hard_delete_conversation(conversation_id=1, user_id=1, tenant_id=1)

        # Verify: execute called for DELETE messages
        assert mock_db.execute.called, "Messages should be deleted first"
        # Verify: delete called for conversation
        assert mock_db.delete.called, "Conversation should be deleted"
        # Verify: commit called
        assert mock_db.commit.called, "Changes should be committed"


class TestGDPRAuditLogging:
    """GDPR operations must be audit logged."""

    @pytest.mark.asyncio
    async def test_hard_delete_creates_audit_log(self):
        """hard_delete_conversation must emit an AuditLogEmitEvent via governance_bus."""
        from src.core.services.cva_service import CVAService
        from src.core.shared.events.governance_events import AuditLogEmitEvent

        mock_conv = MagicMock()
        mock_conv.id = 1

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.delete = AsyncMock()

        emitted: list[object] = []

        async def capture(event: object) -> int:
            emitted.append(event)
            return 1

        service = CVAService(db_session=mock_db, llm_service=AsyncMock())

        with patch(
            "src.core.services.cva_service.governance_bus.emit",
            new=AsyncMock(side_effect=capture),
        ):
            await service.hard_delete_conversation(conversation_id=1, user_id=1, tenant_id=1)

        audit_events = [e for e in emitted if isinstance(e, AuditLogEmitEvent)]
        assert len(audit_events) >= 1, "hard_delete_conversation() must emit AuditLogEmitEvent"


class TestHardDeleteAPIEndpoint:
    """API endpoint for hard delete must exist."""

    def test_hard_delete_endpoint_registered(self):
        """DELETE /conversations/{id}/permanent endpoint must exist."""
        import ast
        from pathlib import Path

        # SP-API migration: endpoint moved to v1/cva/conversations_router.py
        source_path = Path("src/core/api/v1/cva/conversations_router.py")
        source = source_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)

        # Look for delete endpoint that handles hard deletion (messages or permanent)
        found_endpoint = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "delete":
                    if node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and (
                            "permanent" in first_arg.value or "messages" in first_arg.value
                        ):
                            found_endpoint = True
                            break

        assert found_endpoint, (
            "DELETE hard-delete endpoint not found in v1/cva/conversations_router.py. "
            "Required for GDPR Article 17 (Right to Erasure)."
        )

    def test_hard_delete_endpoint_handler(self):
        """Handler function for hard delete must exist."""
        import ast
        from pathlib import Path

        # SP-API migration: handler moved to v1/cva/conversations_router.py
        source_path = Path("src/core/api/v1/cva/conversations_router.py")
        source = source_path.read_text(encoding="utf-8-sig")

        # Check for handler function name
        assert "hard_delete_conversation" in source or "delete_permanent" in source, (
            "Hard delete handler function not found in v1/cva/conversations_router.py"
        )
