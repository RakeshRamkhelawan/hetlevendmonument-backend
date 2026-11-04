import pytest

# Deze tests voeren echt een tool uit en hebben dus een tenant in de executiecontext
# nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for service unit tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


@pytest.mark.unit
class TestHITLStoreDBBacked:
    async def test_create_ticket_calls_repository(self):
        """create_ticket() delegeert naar HITLTicketRepository, niet in-memory."""
        from src.core.tool_broker.hitl_store import HITLStore

        repo_mock = AsyncMock()
        repo_mock.create.return_value = MagicMock(ticket_ref="ticket-42")
        store = HITLStore(repository=repo_mock)

        ticket_id = await store.create_ticket(
            tool_name="email_send", tenant_id=1, user_id=42, payload={"to": "test@example.com"}
        )

        assert ticket_id == "ticket-42"
        assert repo_mock.create.called

    async def test_get_approval_status_reads_from_db(self):
        """get_approval_status() leest uit DB via repository."""
        from src.core.tool_broker.hitl_store import HITLStore

        repo_mock = AsyncMock()
        repo_mock.get.return_value = MagicMock(status="approved")
        store = HITLStore(repository=repo_mock)
        status = await store.get_approval_status(ticket_id="ticket-123", tenant_id=1)
        assert status == "approved"
        repo_mock.get.assert_called_once_with("ticket-123", tenant_id=1)

    async def test_no_in_memory_dict_attribute(self):
        """HITLStore heeft geen _hitl_tickets in-memory dict meer."""
        from src.core.tool_broker.hitl_store import HITLStore

        store = HITLStore(repository=AsyncMock())
        assert not hasattr(store, "_hitl_tickets")
        # Zorg er ook voor dat we de module-level dict controleren in de import
        import src.core.tool_broker.hitl_store as hs

        assert not hasattr(hs, "_hitl_tickets")

    async def test_execute_tool_sees_db_approval(self):
        """execute_tool() ziet goedkeuring die via REST API in DB staat."""
        from src.core.tool_broker.service import ToolBrokerService
        from src.core.tool_broker.risk_classifier import ToolRiskLevel

        hitl_mock = AsyncMock()
        # Sinds ADR-036 OP-63 verzilvert de poort de goedkeuring in EEN UPDATE, met de tool en
        # de parameters in de WHERE, in plaats van alleen de status te lezen.
        hitl_mock.redeem_approval.return_value = True

        service = ToolBrokerService(
            serena_client=AsyncMock(),
            seq_thinking_client=AsyncMock(),
            local_registry=AsyncMock(),
            event_publisher=AsyncMock(),
        )
        # Injecteer de mock hitl_store direct als attribuut
        service.hitl_store = hitl_mock

        # Forceer dat de tool als HIGH risk wordt geclassificeerd
        service.risk_classifier = MagicMock()
        service.risk_classifier.classify.return_value = ToolRiskLevel.HIGH

        local_reg = AsyncMock()
        local_reg.execute_local_tool.return_value = {"success": True}
        service.local_registry = local_reg

        payload = {"_hitl_ticket_ref": "ticket-123", "tenant_id": 1}
        # We gebruiken een bekende test__ prefix om de categorie validatie te passeren
        result = await service.execute_tool(
            tool_name="test__high_risk_tool", payload=payload, agent_id="agent-123"
        )

        hitl_mock.redeem_approval.assert_called_once_with(
            "ticket-123",
            tenant_id=1,
            tool_name="test__high_risk_tool",
            payload={"_hitl_ticket_ref": "ticket-123", "tenant_id": 1},
        )
        assert result == {"success": True}

    async def test_tenant_isolation_hitl_tickets(self):
        """Operator van tenant A kan ticket van tenant B niet zien."""
        from src.core.tool_broker.hitl_store import HITLStore

        repo_mock = AsyncMock()
        repo_mock.get.return_value = None  # Not found voor andere tenant
        store = HITLStore(repository=repo_mock)
        result = await store.get_approval_status(
            ticket_id="ticket-999",
            tenant_id=2,  # tenant 2, ticket van tenant 1
        )
        assert result is None
