import pytest

# Deze tests voeren echt een tool uit en hebben dus een tenant in de executiecontext
# nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.tool_broker.service import ToolBrokerService
from src.core.tool_broker.exceptions import ToolExecutionException


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for service unit tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


@pytest.mark.asyncio
class TestCG004b_ToolBrokerHitlDI:
    def _build_tool_broker(self, hitl_store=None):
        return ToolBrokerService(
            serena_client=AsyncMock(),
            seq_thinking_client=AsyncMock(),
            local_registry=AsyncMock(),
            hitl_store=hitl_store,
        )

    async def test_high_risk_tool_zonder_hitl_store_raise(self):
        """ROOD voor fix: HIGH-risk tool zonder hitl_store raise ToolExecutionException."""
        svc = self._build_tool_broker(hitl_store=None)

        # Mock risk classifier om HIGH te retourneren
        svc.risk_classifier = MagicMock()
        from src.core.tool_broker.risk_classifier import ToolRiskLevel

        svc.risk_classifier.classify = MagicMock(return_value=ToolRiskLevel.HIGH)

        with pytest.raises(ToolExecutionException, match="human approval"):
            await svc.execute_tool("local__high_risk_op", {"tenant_id": 1}, agent_id=None)

    async def test_high_risk_tool_met_approved_ticket_slaagt(self):
        """GROEN na fix: HIGH-risk tool met goedgekeurd ticket wordt uitgevoerd."""
        mock_store = AsyncMock()
        # Sinds ADR-036 OP-63 VERZILVERT de poort de goedkeuring (tool + parameters +
        # eenmalig) in plaats van alleen de status te lezen.
        mock_store.redeem_approval = AsyncMock(return_value=True)
        svc = self._build_tool_broker(hitl_store=mock_store)

        # Mock risk classifier om HIGH te retourneren
        svc.risk_classifier = MagicMock()
        from src.core.tool_broker.risk_classifier import ToolRiskLevel

        svc.risk_classifier.classify = MagicMock(return_value=ToolRiskLevel.HIGH)

        # We moeten ook execute_local_tool mocken of een echte tool gebruiken
        svc.local_registry.execute_local_tool = AsyncMock(return_value={"status": "success"})

        result = await svc.execute_tool(
            "local__high_risk_op",
            {"tenant_id": 1, "_hitl_ticket_ref": "hitl_abc123"},
            agent_id=None,
        )
        mock_store.redeem_approval.assert_awaited_once_with(
            "hitl_abc123",
            tenant_id=1,
            tool_name="local__high_risk_op",
            payload={"tenant_id": 1, "_hitl_ticket_ref": "hitl_abc123"},
        )
        assert result == {"status": "success"}

    async def test_high_risk_tool_met_pending_ticket_blocked(self):
        """GROEN na fix: pending ticket blockt uitvoering."""
        mock_store = AsyncMock()
        # Niet goedgekeurd: de UPDATE raakt nul rijen en `redeem` geeft False.
        mock_store.redeem_approval = AsyncMock(return_value=False)
        svc = self._build_tool_broker(hitl_store=mock_store)

        svc.risk_classifier = MagicMock()
        from src.core.tool_broker.risk_classifier import ToolRiskLevel

        svc.risk_classifier.classify = MagicMock(return_value=ToolRiskLevel.HIGH)

        with pytest.raises(ToolExecutionException, match="requires human approval"):
            await svc.execute_tool(
                "local__high_risk_op",
                {"tenant_id": 1, "_hitl_ticket_ref": "hitl_abc123"},
                agent_id=None,
            )

    async def test_geen_lazy_import_bij_elke_aanroep(self):
        """Regressie: hitl_store wordt niet meer lazily geconstrueerd via getattr."""
        mock_store = AsyncMock()
        svc = self._build_tool_broker(hitl_store=mock_store)
        assert svc.hitl_store is mock_store

    async def test_tenant_isolatie_hitl_status_check(self):
        """Tenant A kan ticket van tenant B niet zien via status-check.

        De tenant voor die status-check komt sinds BE-AGT-045 ronde 2 uit de EXECUTIECONTEXT en
        niet uit de payload. Deze test gaf hem eerder mee als `payload={"tenant_id": 2}` -- dat
        was de NOOIT-regel uit CLAUDE.md (tenant_id nooit uit een request/payload) en het
        betekende dat een aanroeper zelf kon kiezen namens welke tenant hij een ticket opvroeg.
        De eigenschap is nu sterker: de payload kan er niet meer naar vragen. De assertie
        hieronder is ongewijzigd; alleen de herkomst van de 2 is dat wel.
        """
        mock_store = AsyncMock()
        calls: list = []

        async def tracked_redeem(ticket_ref, *, tenant_id, tool_name, payload):
            calls.append({"ticket_ref": ticket_ref, "tenant_id": tenant_id})
            return tenant_id == 1

        mock_store.redeem_approval = AsyncMock(side_effect=tracked_redeem)
        svc = self._build_tool_broker(hitl_store=mock_store)

        svc.risk_classifier = MagicMock()
        from src.core.tool_broker.risk_classifier import ToolRiskLevel

        svc.risk_classifier.classify = MagicMock(return_value=ToolRiskLevel.HIGH)

        # Tenant 2 probeert ticket te gebruiken (dat in onze mock alleen voor tenant 1 'approved'
        # geeft). De 2 komt uit de executiecontext; de payload noemt bewust een ANDERE tenant om
        # aan te tonen dat die niet meer meetelt.
        with pytest.raises(ToolExecutionException):
            await svc.execute_tool(
                "local__op",
                {"tenant_id": 1, "_hitl_ticket_ref": "hitl_tenant1"},
                agent_id=None,
                context={"tenant_id": 2},
            )
        assert calls[0]["tenant_id"] == 2
