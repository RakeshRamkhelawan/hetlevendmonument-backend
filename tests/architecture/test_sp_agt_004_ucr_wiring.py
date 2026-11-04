"""
Architecture tests: SP-AGT-004 -- UnifiedCapabilityRegistry wiring.

Regressiebewakers die permanent groen moeten blijven.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_UCR_FILE = _REPO_ROOT / "src" / "core" / "agents" / "capability_registry.py"


@pytest.mark.unit
def test_unified_capability_registry_module_exists() -> None:
    """capability_registry.py moet aanwezig zijn -- SP-AGT-004."""
    assert _UCR_FILE.exists(), "SP-AGT-004: src/core/agents/capability_registry.py ontbreekt"


@pytest.mark.unit
def test_unified_capability_registry_class_present() -> None:
    """UnifiedCapabilityRegistry class moet gedeclareerd zijn -- SP-AGT-004."""
    source = _UCR_FILE.read_text(encoding="utf-8")
    assert "class UnifiedCapabilityRegistry" in source, (
        "SP-AGT-004: class UnifiedCapabilityRegistry niet gevonden in capability_registry.py"
    )


@pytest.mark.unit
def test_ucr_implements_icapability_registry_at_import() -> None:
    """isinstance(UCR(), ICapabilityRegistry) moet True zijn -- SP-AGT-004."""
    from src.core.agents.api import ICapabilityRegistry
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    assert isinstance(ucr, ICapabilityRegistry), (
        "SP-AGT-004: UnifiedCapabilityRegistry voldoet niet aan ICapabilityRegistry Protocol"
    )


@pytest.mark.unit
def test_ucr_no_direct_db_import() -> None:
    """capability_registry.py mag src.core.database niet direct importeren -- ADR-034."""
    source = _UCR_FILE.read_text(encoding="utf-8")
    assert "src.core.database" not in source, (
        "SP-AGT-004: capability_registry.py importeert src.core.database direct -- ADR-034 verbiedt dit"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_returns_list_not_internal_reference() -> None:
    """discover() mag geen mutable interne state lekken -- SP-AGT-004 security."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry
    from src.core.shared.interfaces import AgentCapability

    ucr = UnifiedCapabilityRegistry()
    ucr._register(tenant_id=1, capability=AgentCapability(name="test-cap", description="test"))
    snapshot = await ucr.discover(query="", tenant_id=1)
    snapshot.clear()
    result = await ucr.discover(query="", tenant_id=1)
    assert len(result) == 1, "SP-AGT-004: discover() lekte interne state"


@pytest.mark.unit
def test_ucr_constructable_with_redis_cache() -> None:
    """UCR + RedisCapabilityCache aanmaken gooit geen exception -- SP-AGT-004 Dag 3."""
    from src.core.agents.adapters.redis_capability_cache import RedisCapabilityCache
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    cache = RedisCapabilityCache()
    ucr = UnifiedCapabilityRegistry(cache=cache)
    assert ucr is not None, "SP-AGT-004 Dag 3: UCR+RedisCapabilityCache constructie mislukt"
