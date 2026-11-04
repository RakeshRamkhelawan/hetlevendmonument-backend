"""
Lazy-import regression tests for the agents router.

Verifies that importing the agents domain router does not eagerly load
heavy modules such as AgentRegistry, so that dev startup stays under
ADR-009's 30s budget.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture
def fail_on_agent_registry() -> Any:
    """Return a side-effect that raises if AgentRegistry is imported."""
    real_import = __builtins__["__import__"]  # type: ignore[index]

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "src.core.agents.agent_registry":
            raise AssertionError(
                f"Heavy module {name} was imported while loading agents router"
            )
        return real_import(name, globals, locals, fromlist, level)

    return guarded_import


@contextmanager
def _dropped(*prefixes: str) -> Iterator[None]:
    """Verwijder modules uit `sys.modules` en zet ze daarna TERUG (ADR-036 OP-45).

    Deze tests moeten vanaf een lege importcache beginnen, anders bewijzen ze niets over wat het
    importeren aanraakt. Tot 2026-08-04 verwijderden ze die modules zonder herstel, en dat lekt naar
    elke andere test in dezelfde xdist-worker: het opnieuw importeren maakt NIEUWE moduleobjecten,
    terwijl elke module die al een naam uit dat pakket had geimporteerd de OUDE objecten vasthoudt.
    Een `is`-vergelijking tussen die twee is daarna vals terwijl ze identiek printen.

    Bij de CVA-variant van deze test is dat aantoonbaar misgegaan (zie
    `tests/unit/api/v1/cva/test_cva_router_lazy_import.py`): het brak
    `test_chat_with_cva_returns_cva_chat_response` in een andere map, maar alleen wanneer het
    toeval die tests in dezelfde worker zette. Hier is geen slachtoffer aangetroffen; het herstel
    staat er omdat het dezelfde constructie is en het lek niet van een slachtoffer afhangt.
    """
    saved = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    }
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in [
            n
            for n in list(sys.modules)
            if any(n == prefix or n.startswith(prefix + ".") for prefix in prefixes)
        ]:
            del sys.modules[name]
        sys.modules.update(saved)


def test_agents_domain_router_imports_without_agent_registry(
    fail_on_agent_registry: Any,
) -> None:
    """Importing the agents domain router must not load AgentRegistry."""
    with _dropped("src.core.api.v1.agents"):
        with patch("builtins.__import__", side_effect=fail_on_agent_registry):
            import src.core.api.v1.agents  # noqa: F401


def test_agent_endpoints_imports_without_agent_registry(
    fail_on_agent_registry: Any,
) -> None:
    """Importing the legacy agent_endpoints module must not load AgentRegistry."""
    with _dropped("src.core.api.agent_endpoints"):
        with patch("builtins.__import__", side_effect=fail_on_agent_registry):
            import src.core.api.agent_endpoints  # noqa: F401
