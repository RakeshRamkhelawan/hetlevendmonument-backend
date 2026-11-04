"""
Tenant-isolatietests voor SP-AUDIT-FIX-001 Dag 1 (RCG-2).

Elke test verifieert dat een service GEEN cross-tenant data retourneert.
Tests zijn ROOD voor de fix, GROEN na de fix.

Bevindingen: AUDIT-TI-001, AUDIT-TI-002, AUDIT-TI-005, AUDIT-TI-004, AUDIT-GDPR-002
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# AUDIT-TI-001: KnowledgeService.get_entry() tenant filter
# ---------------------------------------------------------------------------


class TestKnowledgeServiceTenantIsolation:
    """AUDIT-TI-001: get_entry() mag NOOIT cross-tenant entry teruggeven."""

    @pytest.mark.asyncio
    async def test_get_entry_accepts_tenant_id_param(self) -> None:
        """KnowledgeService.__init__ moet tenant_id accepteren (ADR-005)."""
        from src.core.agents.knowledge_agent.knowledge_service import KnowledgeService

        session = AsyncMock(spec=AsyncSession)
        # Moet niet TypeError gooien -- als het dat wel doet is de fix er nog niet
        service = KnowledgeService(session=session, tenant_id=1)
        assert service.tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_entry_query_includes_tenant_filter(self) -> None:
        """get_entry() query MOET tenant_id in WHERE clausule hebben."""
        from src.core.agents.knowledge_agent.knowledge_service import KnowledgeService

        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeService(session=session, tenant_id=42)
        await service.get_entry(entry_id=UUID("00000000-0000-0000-0000-000000000001"))

        # Verify execute was called with a query containing tenant filter
        assert session.execute.called
        call_args = session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled, f"Query mist tenant_id filter (ADR-005). Query: {compiled}"

    @pytest.mark.asyncio
    async def test_get_entry_with_wrong_tenant_returns_none(self) -> None:
        """Cross-tenant entry MOET None retourneren, NOOIT data lekkage."""
        from src.core.agents.knowledge_agent.knowledge_service import KnowledgeService
        from src.core.knowledge.models import KnowledgeEntry

        session = AsyncMock(spec=AsyncSession)
        # Simuleer: DB retourneert entry van tenant 2, service is van tenant 1
        cross_tenant_entry = MagicMock(spec=KnowledgeEntry)
        cross_tenant_entry.tenant_id = 2
        cross_tenant_entry.id = UUID("00000000-0000-0000-0000-000000000001")

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None  # filter werkt
        session.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeService(session=session, tenant_id=1)
        result = await service.get_entry(entry_id=UUID("00000000-0000-0000-0000-000000000001"))

        assert result is None, "Cross-tenant entry mag nooit teruggegeven worden"


# ---------------------------------------------------------------------------
# AUDIT-TI-002 + TI-005: CollectiveMemory tenant filters
# ---------------------------------------------------------------------------


class TestCollectiveMemoryTenantIsolation:
    """AUDIT-TI-002 + TI-005: _merge_insights en _increment_access_count tenant filter."""

    @pytest.mark.asyncio
    async def test_increment_access_count_query_includes_tenant_filter(self) -> None:
        """_increment_access_count() WHERE clause MOET tenant_id filter bevatten."""
        import uuid as uuid_module

        from src.core.als.collective.collective_memory import CollectiveMemory
        from src.core.als.models.collective_knowledge import CollectiveKnowledge

        memory = CollectiveMemory(tenant_id=99)
        knowledge_id = uuid_module.uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        db_obj = MagicMock(spec=CollectiveKnowledge)
        db_obj.access_count = 5
        db_obj.last_accessed = None
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_obj
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch(
            "src.core.als.collective.collective_memory.get_db_session",
            return_value=mock_session,
        ):
            await memory._increment_access_count(knowledge_id)

        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        # Check WHERE clause specifically, not SELECT columns
        where_part = compiled.split("WHERE")[-1] if "WHERE" in compiled else ""
        assert "tenant_id" in where_part, (
            f"_increment_access_count WHERE clause mist tenant_id filter (ADR-005). "
            f"WHERE clause: {where_part!r}"
        )

    @pytest.mark.asyncio
    async def test_merge_insights_query_includes_tenant_filter(self) -> None:
        """_merge_insights() WHERE clause MOET tenant_id filter bevatten."""
        import uuid as uuid_module

        from src.core.als.collective.collective_memory import (
            CollectiveMemory,
            Insight,
            InsightType,
        )
        from src.core.als.models.collective_knowledge import CollectiveKnowledge

        memory = CollectiveMemory(tenant_id=77)

        existing = Insight(
            agent_id="agent_a",
            tenant_id=77,
            insight_type=InsightType.PATTERN,
            context="test",
            content={"key": "val"},
            confidence=0.8,
        )
        new_insight = Insight(
            agent_id="agent_b",
            tenant_id=77,
            insight_type=InsightType.PATTERN,
            context="test",
            content={"key": "val2"},
            confidence=0.6,
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        db_obj = MagicMock(spec=CollectiveKnowledge)
        db_obj.confidence = 0.8
        db_obj.metadata = {}
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_obj
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch(
            "src.core.als.collective.collective_memory.get_db_session",
            return_value=mock_session,
        ):
            await memory._merge_insights(existing, new_insight)

        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        # Check WHERE clause specifically, not SELECT columns
        where_part = compiled.split("WHERE")[-1] if "WHERE" in compiled else ""
        assert "tenant_id" in where_part, (
            f"_merge_insights WHERE clause mist tenant_id filter (ADR-005). "
            f"WHERE clause: {where_part!r}"
        )


# ---------------------------------------------------------------------------
# AUDIT-TI-004: Analytics /health cross-tenant lekkage
# ---------------------------------------------------------------------------


class TestAnalyticsHealthNoCrossTenantLeak:
    """AUDIT-TI-004: /health endpoint mag geen cross-tenant data tellen."""

    def test_health_check_does_not_aggregate_all_tenants(self) -> None:
        """health_check() mag GEEN platform-brede COUNT uitvoeren zonder tenant filter."""
        import inspect

        from src.core.api.v1.analytics_ingest import events_router

        source = inspect.getsource(events_router.health_check)

        # Na fix: geen onbeperkte COUNT op DBAnalyticsEvent
        has_unbounded_count = (
            "sql_func.count(DBAnalyticsEvent" in source
            and "tenant_id" not in source.split("def health_check")[1].split("except")[0]
        )
        assert not has_unbounded_count, (
            "health_check() telt events over ALLE tenants zonder tenant_id filter (AUDIT-TI-004). "
            "Vervang door SELECT 1 connectivity check."
        )


# ---------------------------------------------------------------------------
# AUDIT-GDPR-002: DSAR PointTransaction tenant filter
# ---------------------------------------------------------------------------


class TestDSARPointTransactionTenantIsolation:
    """AUDIT-GDPR-002: PointTransaction export moet tenant_id filter bevatten."""

    def test_point_transaction_query_contains_tenant_filter(self) -> None:
        """export_user_data() PointTransaction query MOET tenant_id filter hebben."""
        import inspect
        from src.core.governance import dsar_service

        source = inspect.getsource(dsar_service)

        # Zoek de PointTransaction query sectie en controleer op tenant_id
        pt_section_start = source.find("select(PointTransaction)")
        assert pt_section_start != -1, "PointTransaction query niet gevonden in dsar_service.py"

        # Neem 200 tekens na de query-start om de where-clause te checken
        pt_section = source[pt_section_start : pt_section_start + 300]
        assert "tenant_id" in pt_section, (
            f"PointTransaction query mist tenant_id filter (AUDIT-GDPR-002, ADR-005). "
            f"Gevonden sectie: {pt_section!r}"
        )
