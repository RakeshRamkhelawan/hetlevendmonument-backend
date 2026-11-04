import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# BE-AGT-042: het pack-pad is fail-closed zonder verantwoordelijke mens. In productie
# komt die van de HTTP-ingang; hier expliciet, zodat de test het echte pad volgt.
TEST_INITIATOR = 42

from src.core.als.enterprise.packs import DomainPack, DomainPackOrchestrator, WorkflowStep
from src.core.shared.interfaces import ExecutionResult, ExecutionStatusContract


@pytest.mark.asyncio
async def test_domain_pack_execution_flow():
    """Test domain pack execution with mocked dependencies"""
    # 1. Setup Pack Definition
    pack = DomainPack(
        pack_id="pack.finance.compliance",
        name="Finance Compliance Pack",
        steps=[
            WorkflowStep(agent_id="audit_compliance", mode="sequential"),
            WorkflowStep(agent_id="tax_compliance", mode="parallel"),
            WorkflowStep(agent_id="forecasting", mode="parallel"),
        ],
    )

    # 2. Mock Agent Execution - define before engine creation
    async def mock_agent_call(agent_id, tenant_id, params, *, initiated_by_user_id=None):
        # initiated_by_user_id hoort sinds BE-AGT-042 bij de signatuur van _execute_step;
        # de mock accepteert hem zodat hij het echte contract blijft nabootsen.
        await asyncio.sleep(0.01)
        return ExecutionResult(
            task_id="t1",
            success=True,
            result_data={"agent_id": agent_id},
            tenant_id=tenant_id,
        )

    # 3. Create engine and mock _execute_step and db_manager to avoid DB pollution
    engine = DomainPackOrchestrator()

    mock_db_session = AsyncMock()
    mock_db_cm = MagicMock()
    mock_db_cm.__aenter__ = AsyncMock(return_value=mock_db_session)
    mock_db_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(engine, "_execute_step", side_effect=mock_agent_call),
        patch("src.core.database.database.db_manager") as mock_db_manager,
    ):
        mock_db_manager.get_session.return_value = mock_db_cm
        results = await engine.run_pack(pack, tenant_id=1, initiated_by_user_id=TEST_INITIATOR)

        # Verify all steps executed
        assert len(results) == 3
        # Check if audit_compliance executed
        assert any(r.result_data.get("agent_id") == "audit_compliance" for r in results)


@pytest.mark.asyncio
async def test_domain_pack_sla_timeout():
    pack = DomainPack(
        pack_id="pack.slow",
        name="Slow Pack",
        steps=[WorkflowStep(agent_id="slow_agent", sla_seconds=0.01)],
    )

    engine = DomainPackOrchestrator()

    async def very_slow_call(*args, **kwargs):
        # Ronde 3 (verplichte blinde eindreview): de oorspronkelijke `*args`-only
        # signatuur accepteerde de keyword-only `initiated_by_user_id` niet, dus
        # _run_single_step()'s aanroep gooide direct een TypeError -- deze test
        # bereikte de echte TimeoutError-tak nooit en slaagde alleen omdat "timeout"
        # toevallig een substring is van de eigen testnaam (sla_timeout) in die
        # TypeError-tekst. `**kwargs` laat de coroutine daadwerkelijk 0.1s slapen
        # zodat asyncio.wait_for(timeout=0.01) hem echt afbreekt.
        await asyncio.sleep(0.1)
        return ExecutionResult(task_id="t1", success=True)

    with (
        patch.object(DomainPackOrchestrator, "_execute_step", side_effect=very_slow_call),
        patch("src.core.database.database.db_manager"),
    ):
        results = await engine.run_pack(pack, tenant_id=1, initiated_by_user_id=TEST_INITIATOR)
        # Should contain a failed result due to timeout
        assert results[0].success is False
        # ADR-036 D7-001: een SLA-timeout is een onverwachte fout, geen governance-weigering
        # of een deeluitvoering.
        assert results[0].status == ExecutionStatusContract.MISLUKT
        assert "timeout" in results[0].error_message.lower()


@pytest.mark.asyncio
async def test_domain_pack_step_unexpected_exception_reports_mislukt():
    """ADR-036 D7-001 -- gevonden door de verplichte blinde eindreview (ronde 3): de
    generieke `except Exception`-tak in `_run_single_step()` (naast de TimeoutError-tak,
    packs.py:394-401) had geen eigen, doelbewuste test -- hij werd alleen per ongeluk
    geraakt door de kapotte mock-signatuur in `test_domain_pack_sla_timeout` hierboven.
    Deze test raakt de tak direct: `_execute_step` gooit synchroon een RuntimeError,
    wat geen TimeoutError is en dus de sibling-tak moet raken, niet de SLA-tak."""
    pack = DomainPack(
        pack_id="pack.broken",
        name="Broken Pack",
        steps=[WorkflowStep(agent_id="broken_agent", sla_seconds=5)],
    )
    engine = DomainPackOrchestrator()

    with (
        patch.object(
            DomainPackOrchestrator,
            "_execute_step",
            side_effect=RuntimeError("dispatch exploded"),
        ),
        patch("src.core.database.database.db_manager"),
    ):
        results = await engine.run_pack(pack, tenant_id=1, initiated_by_user_id=TEST_INITIATOR)

    assert results[0].success is False
    assert results[0].status == ExecutionStatusContract.MISLUKT
    assert "dispatch exploded" in (results[0].error_message or "")


@pytest.mark.asyncio
async def test_run_pack_by_id_not_found_reports_mislukt():
    """ADR-036 D7-001 -- gevonden door de verplichte blinde eindreview (ronde 3): de
    "pack not found"-tak in `run_pack_by_id()` (packs.py:266-276) had geen enkele test --
    bevestigd met een live mutatie (MISLUKT -> KLAAR gaf 0 gedetecteerde regressies over
    de hele gerichte testset). `run_pack_by_id()` heeft ook geen enkele productie-
    aanroeper (repo-breed gegrept), maar "geen vindbare aanroeper" is geen vrijstelling
    van een correcte status als de tak ooit wel bereikt wordt (zelfde redenering als de
    dag-1-bevinding voor het agent-aanmaak-endpoint)."""
    engine = DomainPackOrchestrator()

    results = await engine.run_pack_by_id("does-not-exist-in-catalog", tenant_id=1)

    assert len(results) == 1
    assert results[0].success is False
    assert "not found" in (results[0].error_message or "").lower()
    assert results[0].status == ExecutionStatusContract.MISLUKT
