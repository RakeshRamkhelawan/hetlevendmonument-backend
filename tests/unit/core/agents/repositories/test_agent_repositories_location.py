"""Test dat agent repositories importeerbaar zijn op de nieuwe locatie.

SP-DSM-COMPLETE Dag 3: repositories verplaatst van database/ naar agents/repositories/.
"""

import pytest


def test_agent_repository_importable_from_new_location() -> None:
    """AgentRepository moet importeerbaar zijn vanuit agents.repositories."""
    from src.core.agents.repositories.agent_repository import AgentRepository

    assert AgentRepository is not None


def test_agent_registry_repository_importable_from_new_location() -> None:
    """AgentRegistryRepository moet importeerbaar zijn vanuit agents.repositories."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    assert AgentRegistryRepository is not None


def test_repositories_package_exports_both() -> None:
    """Het repositories package moet beide klassen exporteren."""
    from src.core.agents import repositories

    assert hasattr(repositories, "AgentRepository")
    assert hasattr(repositories, "AgentRegistryRepository")


def test_agent_repository_has_required_methods() -> None:
    """AgentRepository moet de verplichte methodes hebben."""
    from src.core.agents.repositories.agent_repository import AgentRepository

    assert hasattr(AgentRepository, "get_agent_by_id")
    assert hasattr(AgentRepository, "get_agents_by_tenant")
    assert hasattr(AgentRepository, "save_agent")


def test_agent_registry_repository_has_required_methods() -> None:
    """AgentRegistryRepository moet de verplichte methodes hebben."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    assert hasattr(AgentRegistryRepository, "get_registered_agent_by_agent_id")
    assert hasattr(AgentRegistryRepository, "get_registered_agents")
    assert hasattr(AgentRegistryRepository, "get_active_agents")
    assert hasattr(AgentRegistryRepository, "register_agent")
    assert hasattr(AgentRegistryRepository, "update_agent")
    assert hasattr(AgentRegistryRepository, "delete_agent")


def test_old_database_location_has_no_imports() -> None:
    """Oude database/agent_repository.py bevat geen wrong-direction imports."""
    import ast
    from pathlib import Path

    for filename in ("agent_repository.py", "agent_registry_repository.py"):
        path = Path(f"src/core/database/{filename}")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        agent_imports = [m for m in imports if m.startswith("src.core.agents")]
        assert agent_imports == [], f"{filename} still has agent_runtime imports: {agent_imports}"
