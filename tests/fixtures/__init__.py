"""Lazy module access for the modular test fixture package.

Pytest loads fixture modules listed in ``pytest_plugins`` with assert rewrite.
Importing those modules eagerly from this package causes ``PytestAssertRewriteWarning``
because the modules are already in ``sys.modules`` before pytest rewrites them.

This package therefore exposes fixture modules lazily for direct imports like:

    from tests.fixtures import auth, tenant

while leaving pytest plugin loading to ``tests/conftest.py``.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

_MODULES = {
    "agent_mocks",
    "auth",
    "database",
    "database_mocks",
    "external_mocks",
    "llm_mocks",
    "mocks",
    "tenant",
    "workflow_mocks",
}

__all__ = sorted(_MODULES)


def __getattr__(name: str) -> ModuleType:
    if name in _MODULES:
        return import_module(f"tests.fixtures.{name}")
    raise AttributeError(f"module 'tests.fixtures' has no attribute {name!r}")
