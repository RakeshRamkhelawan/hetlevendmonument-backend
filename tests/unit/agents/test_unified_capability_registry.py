"""
SP-AGT-004 -- RED tests: UnifiedCapabilityRegistry skeleton + Redis-backend.

Test taxonomy:
  Dag 1:
    1.1 -- architecture: UCR implementeert ICapabilityRegistry (runtime_checkable)
    1.2 -- happy path: discover("") geeft alle capabilities voor de tenant
    1.3 -- happy path: discover(query) filtert op naam
    1.4 -- security: tenant-isolatie -- tenant A ziet NIET de capabilities van tenant B
    1.5 -- security: discover() geeft een kopie, geen interne referentie
  Dag 2:
    1.6 -- happy path: register_agent() is publiek async en slaat op in in-memory
    1.7 -- happy path: register_agent() schrijft naar Redis (write-through)
    1.8 -- happy path: discover() laadt vanuit Redis bij in-memory miss (lazy-load)
    1.9 -- resilience: Redis-fout bij register_agent() gooit geen exception
    1.10 -- resilience: Redis-fout bij discover() valt terug op in-memory
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.shared.interfaces import AgentCapability


def _cap(name: str, description: str = "test") -> AgentCapability:
    return AgentCapability(name=name, description=description)


@pytest.mark.unit
def test_ucr_implements_icapability_registry_protocol() -> None:
    """UnifiedCapabilityRegistry moet ICapabilityRegistry implementeren -- SP-AGT-004."""
    from src.core.agents.api import ICapabilityRegistry
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    assert isinstance(ucr, ICapabilityRegistry), (
        "SP-AGT-004: UnifiedCapabilityRegistry moet ICapabilityRegistry implementeren"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_empty_query_returns_all() -> None:
    """discover('', tenant_id) geeft alle capabilities voor die tenant -- SP-AGT-004."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    ucr._register(tenant_id=1, capability=_cap("summarize"))
    ucr._register(tenant_id=1, capability=_cap("translate"))

    result = await ucr.discover(query="", tenant_id=1)
    assert len(result) == 2, "SP-AGT-004: discover('') moet alle capabilities voor de tenant geven"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_filters_by_name() -> None:
    """discover(query) filtert op naam -- SP-AGT-004."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    ucr._register(tenant_id=1, capability=_cap("summarize"))
    ucr._register(tenant_id=1, capability=_cap("translate"))

    result = await ucr.discover(query="summar", tenant_id=1)
    assert len(result) == 1, "SP-AGT-004: query-filter moet alleen matching cap teruggeven"
    assert result[0].name == "summarize"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_isolates_tenants() -> None:
    """Tenant A mag NIET de capabilities van tenant B zien -- SP-AGT-004 security."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    ucr._register(tenant_id=1, capability=_cap("tenant-1-cap"))
    ucr._register(tenant_id=2, capability=_cap("tenant-2-cap"))

    result_t1 = await ucr.discover(query="", tenant_id=1)
    assert len(result_t1) == 1, "SP-AGT-004: tenant 1 mag alleen eigen caps zien"
    assert result_t1[0].name == "tenant-1-cap"

    result_t2 = await ucr.discover(query="", tenant_id=2)
    assert len(result_t2) == 1, "SP-AGT-004: tenant 2 mag alleen eigen caps zien"
    assert result_t2[0].name == "tenant-2-cap"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_returns_copy_not_reference() -> None:
    """discover() mag geen interne state lekken via mutable returnwaarde -- SP-AGT-004."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    ucr._register(tenant_id=1, capability=_cap("summarize"))

    snapshot = await ucr.discover(query="", tenant_id=1)
    snapshot.clear()

    result = await ucr.discover(query="", tenant_id=1)
    assert len(result) == 1, (
        "SP-AGT-004: discover() lekte interne state -- returnwaarde moet een kopie zijn"
    )


# ---------------------------------------------------------------------------
# Dag 2 tests -- ICacheBackend injectie
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_register_agent_public_stores_in_memory() -> None:
    """register_agent() is publiek async en capability is daarna via discover() vindbaar -- SP-AGT-004 Dag 2."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    mock_cache = AsyncMock()
    ucr = UnifiedCapabilityRegistry(cache=mock_cache)
    cap = _cap("summarize")

    await ucr.register_agent(tenant_id=1, capability=cap)

    result = await ucr.discover(query="summarize", tenant_id=1)
    assert len(result) == 1, (
        "SP-AGT-004 Dag 2: register_agent() moet capability opslaan in in-memory"
    )
    assert result[0].name == "summarize"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_register_agent_writes_to_cache() -> None:
    """register_agent() schrijft capability naar cache met correcte key-prefix -- SP-AGT-004 Dag 2."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    mock_cache = AsyncMock()
    ucr = UnifiedCapabilityRegistry(cache=mock_cache)
    cap = _cap("summarize")

    await ucr.register_agent(tenant_id=1, capability=cap)

    mock_cache.set.assert_called_once()
    key = mock_cache.set.call_args[0][0]
    assert "ucr:1:" in key, f"SP-AGT-004 Dag 2: cache key moet 'ucr:1:' bevatten, was: {key!r}"
    assert "summarize" in key, (
        f"SP-AGT-004 Dag 2: cache key moet capability naam bevatten, was: {key!r}"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_lazy_loads_from_cache_on_memory_miss() -> None:
    """discover() laadt capabilities vanuit cache als in-memory leeg is -- SP-AGT-004 Dag 2."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    cap = _cap("translate")
    mock_cache = AsyncMock()
    mock_cache.keys.return_value = ["ucr:1:translate"]
    mock_cache.get.return_value = cap.model_dump_json()

    ucr = UnifiedCapabilityRegistry(cache=mock_cache)

    result = await ucr.discover(query="", tenant_id=1)
    assert len(result) == 1, (
        "SP-AGT-004 Dag 2: discover() moet lazy-loaden vanuit cache bij memory miss"
    )
    assert result[0].name == "translate"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_register_agent_cache_failure_does_not_raise() -> None:
    """Cache-fout bij register_agent() gooit geen exception; in-memory blijft intact -- SP-AGT-004 Dag 2."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    mock_cache = AsyncMock()
    mock_cache.set.side_effect = ConnectionError("cache down")
    ucr = UnifiedCapabilityRegistry(cache=mock_cache)

    await ucr.register_agent(tenant_id=1, capability=_cap("summarize"))

    result = await ucr.discover(query="", tenant_id=1)
    assert len(result) == 1, "SP-AGT-004 Dag 2: in-memory moet intact zijn na cache-fout"
    mock_cache.keys.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_discover_cache_failure_returns_empty_gracefully() -> None:
    """Cache-fout tijdens lazy-load leidt tot lege lijst, geen exception -- SP-AGT-004 Dag 2."""
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    mock_cache = AsyncMock()
    mock_cache.keys.side_effect = ConnectionError("cache down")
    ucr = UnifiedCapabilityRegistry(cache=mock_cache)

    result = await ucr.discover(query="", tenant_id=1)
    assert result == [], "SP-AGT-004 Dag 2: cache-fout mag geen exception gooien"
