"""Unit tests for agent repository deprecation shims."""

import importlib


def test_agent_repository_shim_module():
    """Validates src.core.database.agent_repository module imports and points to new location."""
    mod = importlib.import_module("src.core.database.agent_repository")
    assert mod.__doc__ is not None
    assert "src.core.agents.repositories" in mod.__doc__


def test_agent_registry_repository_shim_module():
    """Validates src.core.database.agent_registry_repository module imports and points to new location."""
    mod = importlib.import_module("src.core.database.agent_registry_repository")
    assert mod.__doc__ is not None
    assert "src.core.agents.repositories" in mod.__doc__
