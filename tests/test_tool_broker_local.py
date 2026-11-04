# TODO(SP-VOLGENDE): dit legacy smoke-testbestand (buiten de officiele poort -- het staat
# los in tests/, niet onder tests/unit|architecture|core|contracts) faalde al voor deze sessie
# op de tenant_id-eis van ToolBrokerService (pre-existing, geverifieerd tegen develop e71cc3c5
# in een schone worktree: dezelfde 2 failures, los van dit bestand haar wijzigingen). De
# set_tenant_id-fix hieronder is echt en neemt die eerste laag weg. Een TWEEDE, dieper gat is
# tijdens die reparatie ontdekt en NIET opgelost: `execute_tool` weigert daarna alsnog met
# "Agent 'None' is not authorized" -- deze test geeft geen agent_id mee en er is geen
# permissieprofiel in config/tool_permissions.yml gevonden dat local__read_file expliciet
# toestaat. Dat is een ander onderzoek (welke identiteit hoort dit legacy-pad te gebruiken)
# dan OP-216 (dode sandbox-constructie) en wordt hier niet als bijvangst gefixt.
import asyncio
from collections.abc import Iterator

import pytest

from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService


@pytest.fixture(autouse=True)
def _clean_tenant_context() -> Iterator[None]:
    """Zie test_pseudonymisation_leaks.py: zonder dit lekt de tenant naar latere tests (OP-20)."""
    set_tenant_id(None)
    yield
    set_tenant_id(None)


@pytest.mark.asyncio
async def test_tool_broker_local_read_file(tmp_path):
    set_tenant_id(1)

    # 1. Create a whitelisted test file
    test_file = tmp_path / "src/core/test.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("Hello from ToolBroker!")

    # 2. Setup Registry with custom config if needed, or rely on defaults
    # For testing, we mock the path check or ensure it matches
    registry = LocalToolRegistry()
    # Override whitelist for test stability if needed
    registry.whitelist["allowed_paths"].append(str(tmp_path))

    # 3. Setup Service
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=registry,
        enable_resilience=False,
    )

    # 4. Execute Local Tool
    result = await service.execute_tool("local__read_file", {"path": str(test_file)})

    # 5. Verify
    assert result["success"] is True
    assert "Hello from ToolBroker!" in result["content"]


@pytest.mark.asyncio
async def test_tool_broker_local_security_block():
    set_tenant_id(1)

    registry = LocalToolRegistry()
    service = ToolBrokerService(
        serena_client=None, seq_thinking_client=None, local_registry=registry
    )

    # Attempt to read a forbidden file (/etc/passwd style)
    result = await service.execute_tool("local__read_file", {"path": "/etc/passwd"})

    assert result["success"] is False
    assert "Access Denied" in result["error"]
