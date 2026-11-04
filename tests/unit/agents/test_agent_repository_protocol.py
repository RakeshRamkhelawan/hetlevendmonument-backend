"""Tests -- SP-AGT-002 Dag 3 -- Repository Protocol Layer.

Defines the contract for the repository pattern in src/core/agents/.
All tests GREEN after implementation in commit c27dbc03.
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock

from src.core.shared.interfaces import (
    IAgentRegistryRepository,
    IAgentRepository,
    IRedisRepository,
)
from src.core.agents.repositories.agent_repository import AgentRepository


def test_iagent_repository_protocol_exists() -> None:
    """IAgentRepository Protocol must exist in src.core.shared.interfaces."""
    assert IAgentRepository is not None


def test_iagent_repository_has_required_methods() -> None:
    """IAgentRepository must declare get_agent_by_id, get_agents_by_tenant, save_agent."""
    for method in ("get_agent_by_id", "get_agents_by_tenant", "save_agent"):
        assert hasattr(IAgentRepository, method), f"IAgentRepository missing method: {method}"


def test_iagent_registry_repository_has_required_methods() -> None:
    """IAgentRegistryRepository must declare all 6 required methods."""
    for method in (
        "get_registered_agent_by_agent_id",
        "get_registered_agents",
        "get_active_agents",
        "register_agent",
        "update_agent",
        "delete_agent",
    ):
        assert hasattr(IAgentRegistryRepository, method), (
            f"IAgentRegistryRepository missing method: {method}"
        )


def test_iredis_repository_has_required_methods() -> None:
    """IRedisRepository must declare get, set, delete."""
    for method in ("get", "set", "delete"):
        assert hasattr(IRedisRepository, method), f"IRedisRepository missing method: {method}"


def test_agent_repository_concrete_implements_protocol() -> None:
    """Concrete AgentRepository must satisfy IAgentRepository at runtime.

    NOTE: runtime_checkable Protocol only checks that the required method *names*
    exist on the class -- it does not verify signatures or async-ness.
    Full structural conformance is verified by pyright at type-check time.
    """
    mock_session = AsyncMock()
    instance = AgentRepository(mock_session)
    assert isinstance(instance, IAgentRepository), (
        "AgentRepository does not structurally satisfy IAgentRepository protocol"
    )


def test_base_agent_has_no_database_import() -> None:
    """base_agent.py must not import from src.core.database (use repository protocol instead)."""
    base_agent_path = (
        Path(__file__).parent.parent.parent.parent / "src" / "core" / "agents" / "base_agent.py"
    )
    source = base_agent_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    db_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "src.core.database" in node.module:
                db_imports.append(f"L{node.lineno}: from {node.module} import ...")

    assert not db_imports, (
        f"base_agent.py still imports directly from src.core.database -- "
        f"use IAgentRepository protocol instead: {db_imports}"
    )
