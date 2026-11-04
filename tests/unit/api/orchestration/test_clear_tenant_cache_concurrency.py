"""Regressie-vangnet -- SP-ADR023-002 Dag 3 -- clear_tenant_cache() non-atomiciteit.

Legt het BESTAANDE, al gedocumenteerde gedrag vast (dependencies.py:118-124 NOTE):
de 4 evictions in clear_tenant_cache() zijn niet atomair als groep -- een
gelijktijdig verzoek kan een cache tussen twee evictions weer vullen. Dit is geen
herontwerp, alleen een test die het geaccepteerde gedrag expliciet documenteert
zodat een toekomstige wijziging die dit per ongeluk "fixt" of erger maakt, opvalt.
"""

from __future__ import annotations
from typing import Any
from unittest.mock import MagicMock

import pytest

import src.core.api.v1.orchestration.dependencies as dep_module


@pytest.mark.unit
def test_clear_tenant_cache_does_not_atomically_guard_against_concurrent_repopulation() -> None:
    """Simuleert een gelijktijdig verzoek dat _critic_cache opnieuw vult NADAT
    clear_tenant_cache() die specifieke cache al heeft leeggemaakt (via een
    dict-subclass die op de events van de LAATSTE evictie in de reeks inhaakt).
    De resterende caches moeten nog steeds correct leeg zijn."""
    tenant_id = 88920
    concurrently_created_agent = MagicMock(name="concurrently_created_critic_agent")

    class _RepopulatingDict(dict):  # type: ignore[type-arg]
        """Mimics a concurrent request creating a new AgentHealthMonitorAgent
        for this tenant during the health-monitor eviction step -- the LAST
        step in clear_tenant_cache()'s sequence, so nothing runs afterward to
        catch the repopulation."""

        def pop(self, *args: Any, **kwargs: Any) -> Any:
            result = super().pop(*args, **kwargs)
            dep_module._critic_cache[tenant_id] = concurrently_created_agent
            return result

    original_critic = dep_module._critic_cache
    original_health = dep_module._health_monitor_cache
    dep_module._critic_cache = {tenant_id: MagicMock(name="stale_critic_agent")}
    dep_module._health_monitor_cache = _RepopulatingDict(
        {tenant_id: MagicMock(name="stale_health_monitor")}
    )
    try:
        dep_module.clear_tenant_cache(tenant_id)

        assert tenant_id not in dep_module._health_monitor_cache, (
            "_health_monitor_cache must be empty after clear_tenant_cache() -- "
            "this is the LAST eviction step, nothing races against it here."
        )
        assert dep_module._critic_cache.get(tenant_id) is concurrently_created_agent, (
            "REGRESSIE: clear_tenant_cache() is NIET langer expliciet niet-atomair -- "
            "als dit assert nu faalt omdat _critic_cache leeg is, is het gedrag "
            "veranderd (mogelijk verbeterd, mogelijk kapot); pas de docstring op "
            "dependencies.py::clear_tenant_cache() aan en herzie deze test bewust, "
            "in plaats van hem stilzwijgend te laten falen."
        )
    finally:
        dep_module._critic_cache = original_critic
        dep_module._health_monitor_cache = original_health
