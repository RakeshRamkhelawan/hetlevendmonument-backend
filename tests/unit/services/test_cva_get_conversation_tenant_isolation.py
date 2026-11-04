"""FA-001: get_conversation() ConversationMessage query MOET tenant_id filter bevatten.

Defense-in-depth: _get_conversation() gate voorkomt cross-tenant toegang nu,
maar elke ConversationMessage query moet zelf ook filteren op tenant_id (SEC-008 principe).
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestGetConversationTenantIsolation:
    """get_conversation() messages query filtert op tenant_id (FA-001)."""

    @pytest.mark.asyncio
    async def test_get_conversation_messages_query_includes_tenant_id_filter(self):
        """ConversationMessage query in get_conversation() MOET WHERE tenant_id bevatten."""
        from src.core.services.cva_service import CVAService

        executed_queries: list[object] = []

        mock_db = AsyncMock()

        mock_conv = MagicMock()
        mock_conv.id = 5
        mock_conv.title = "Test conversation"
        mock_conv.agent_id = None
        mock_conv.is_active = True
        mock_conv.created_at = None
        mock_conv.updated_at = None

        call_count = 0

        async def capture_execute(stmt: object, *_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            executed_queries.append(stmt)
            result = MagicMock()
            if call_count == 1:
                # First call: _get_conversation() conversation lookup
                result.scalar_one_or_none.return_value = mock_conv
                result.scalars.return_value.all.return_value = [mock_conv]
            else:
                # Second call: messages query -- this is what we verify
                result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = AsyncMock(side_effect=capture_execute)

        svc = CVAService(db_session=mock_db)
        await svc.get_conversation(conversation_id=5, user_id=1, tenant_id=2)

        assert call_count >= 2, (
            "get_conversation() voerde minder dan 2 queries uit. "
            "Verwacht: 1 conversation-lookup + 1 messages-query."
        )

        # The LAST execute call must be the ConversationMessage query
        from sqlalchemy.sql import ClauseElement

        messages_query = executed_queries[-1]
        if isinstance(messages_query, ClauseElement):
            query_str = str(messages_query.compile(compile_kwargs={"literal_binds": True}))
        else:
            query_str = str(messages_query)

        assert re.search(r"where\b.*tenant_id", query_str.lower(), re.DOTALL), (
            "get_conversation() ConversationMessage query bevat geen tenant_id filter. "
            "FA-001: voeg ConversationMessage.tenant_id == tenant_id toe aan de WHERE predicate."
        )
