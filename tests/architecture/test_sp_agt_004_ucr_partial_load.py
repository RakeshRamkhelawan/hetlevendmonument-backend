"""
SP-AGT-004 Dag 4 FA-003 fix -- UCR partial-load reset.

Verifieert dat _loaded teruggezet wordt als _load_from_cache mislukt,
zodat een volgende discover() opnieuw probeert te laden.

best_effort swallows alle exceptions (geen re-raise). Als keys() een
ConnectionError gooit, vangt best_effort het op, en loaded_ok blijft False.
discover() moet dan _loaded.discard(tenant_id) aanroepen.
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_loaded_guard_resets_on_partial_cache_failure() -> None:
    """_loaded wordt gediscard als _load_from_cache False retourneert.

    FA-003 (SP-AGT-004 Dag 2 final-approver): tenant mag niet permanent in
    _loaded staan bij partial cache failure.
    """
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    mock_cache = AsyncMock()
    mock_cache.keys = AsyncMock(side_effect=ConnectionError("Redis down"))
    ucr = UnifiedCapabilityRegistry(cache=mock_cache)

    result = await ucr.discover(query="", tenant_id=1)

    assert len(result) == 0
    assert 1 not in ucr._loaded, (
        "SP-AGT-004 FA-003: _loaded mag niet gezet zijn na partial cache failure. "
        "Fix: _loaded.discard(tenant_id) in discover() na mislukte _load_from_cache."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_second_discover_retries_after_load_failure() -> None:
    """Na een mislukte load probeert een tweede discover() opnieuw te laden.

    FA-003: na _loaded.discard() moet de volgende discover() de load herproberen.
    """
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    mock_cache = AsyncMock()
    mock_cache.keys = AsyncMock(side_effect=ConnectionError("Redis down"))
    ucr = UnifiedCapabilityRegistry(cache=mock_cache)

    # Eerste discover: fout -> _loaded moet leeg blijven
    await ucr.discover(query="", tenant_id=1)
    assert 1 not in ucr._loaded

    # Tweede discover: keys succesvol (lege cache), tenant wordt nu wel in _loaded gezet
    mock_cache.keys = AsyncMock(return_value=[])
    await ucr.discover(query="", tenant_id=1)
    assert 1 in ucr._loaded, (
        "SP-AGT-004 FA-003: tweede discover() moet _load herproberen na reset van _loaded."
    )
