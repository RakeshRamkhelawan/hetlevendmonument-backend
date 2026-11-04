"""SEC-008: _get_message_history MOET filteren op tenant_id.

Rode tests -- ROOD totdat SEC-008 fix is geimplementeerd:
- tenant_id als verplichte parameter aan _get_message_history
- WHERE clause filtert op ConversationMessage.tenant_id
"""

import inspect
import re

import pytest


class TestMessageHistoryTenantIsolation:
    """_get_message_history filtert berichten op tenant_id (SEC-008)."""

    def test_get_message_history_accepts_tenant_id_parameter(self):
        """_get_message_history MOET tenant_id als parameter hebben (geen default)."""
        from src.core.services.cva_service import CVAService

        sig = inspect.signature(CVAService._get_message_history)
        params = sig.parameters

        assert "tenant_id" in params, (
            "_get_message_history heeft geen tenant_id parameter. "
            "SEC-008: voeg tenant_id toe als verplichte parameter."
        )
        # tenant_id mag GEEN default waarde hebben (verplicht)
        tenant_param = params["tenant_id"]
        assert tenant_param.default is inspect.Parameter.empty, (
            "_get_message_history.tenant_id heeft een default waarde. "
            "SEC-008: tenant_id moet verplicht zijn (geen default)."
        )

    @pytest.mark.asyncio
    async def test_get_message_history_query_includes_tenant_id_filter(self):
        """_get_message_history query MOET WHERE tenant_id == ... bevatten (SEC-008)."""
        from unittest.mock import AsyncMock, MagicMock

        from src.core.services.cva_service import CVAService

        executed_queries: list[object] = []

        mock_db = AsyncMock()

        async def capture_execute(stmt: object, *_args: object, **_kwargs: object) -> MagicMock:
            executed_queries.append(stmt)
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = AsyncMock(side_effect=capture_execute)

        svc = CVAService(db_session=mock_db)
        # tenant_id=1 -- only messages for this tenant should be returned
        await svc._get_message_history(conversation_id=99, tenant_id=1)  # type: ignore[call-arg]

        assert len(executed_queries) >= 1, "_get_message_history voerde geen query uit."

        # Check that the compiled query contains tenant_id filter
        from sqlalchemy.sql import ClauseElement

        query = executed_queries[-1]
        if isinstance(query, ClauseElement):
            query_str = str(query.compile(compile_kwargs={"literal_binds": True}))
        else:
            query_str = str(query)
        assert re.search(r"where\b.*tenant_id", query_str.lower(), re.DOTALL), (
            "_get_message_history query bevat geen tenant_id filter in de WHERE clause. "
            "SEC-008: voeg ConversationMessage.tenant_id == tenant_id toe aan de WHERE predicate."
        )

    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises_type_error(self):
        """_get_message_history zonder tenant_id argument raised TypeError (SEC-008)."""
        from unittest.mock import AsyncMock

        from src.core.services.cva_service import CVAService

        mock_db = AsyncMock()
        svc = CVAService(db_session=mock_db)

        with pytest.raises(TypeError):
            await svc._get_message_history(conversation_id=1)  # type: ignore[call-arg]
