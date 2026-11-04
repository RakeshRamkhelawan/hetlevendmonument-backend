# BE-AGT-001: AgentHealthMonitorAgent Write-Bridge + RedisRouteCacheTier

**Sprint:** SP-WE-10
**ADR:** ADR-023 (5-tier agent routing, health-aware)
**Bevinding:** CG-005
**Status:** IMPLEMENTED
**Datum:** 2026-06-01

---

## Samenvatting

`AgentHealthMonitorAgent` schrijft nu health-transities terug naar `AgentRouterAgent._manifests`
via een push-model write-bridge. `AgentManifest.health_status` wordt bijgewerkt bij elke
status-transitie. `HealthScorer.score_manifest()` levert daarna correcte penalisaties voor
CRITICAL/WARNING agents in de capability_match sortering.

Aanvullend: `RedisRouteCacheTier` is geimplementeerd als optionele tier 1.5 in de routing-cache
voor cross-worker consistentie.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/agent_health_monitor_agent.py` | `router_ref` parameter, `set_router()`, `_push_to_router()`, `_check_all()` push buiten lock, thread-safe singleton |
| `src/core/agents/agent_router_agent.py` | `RedisRouteCacheTier` klasse, `update_health_status()` methode, `_redis_cache_tier` attribuut, `get_agent_router(redis_client=...)` |
| `tests/unit/agents/test_health_write_bridge.py` | 4 TDD tests (write-bridge, scorer, Redis tier, tenant isolatie) |

---

## Architectuurbeslissingen

### A: Push-model (monitor -> router)

Push bij status-transitie (niet elke record). Frequentie laag (O(alerts/10min per agent)).
Write is dict-update achter asyncio.Lock -- sub-microseconde.

### B: Push buiten `self._lock`

Scalaire waarden (agent_id, status, success_rate, avg_latency_ms) worden gekopieerd BINNEN
de lock. De await van `_push_to_router()` vindt BUITEN de lock plaats zodat I/O
(Redis, netwerk) nooit `self._lock` blokkeert.

### C: RedisRouteCacheTier als tier 1.5

In-memory RouteCache blijft tier 1. Redis is additioneel: miss = doorgaan naar tier 2.
Redis-unavailability: warning gelogd, routing gaat ongehinderd door.

---

## Trainingssamenvatting

### Flow 1: AgentHealthMonitorAgent -> AgentRouterAgent manifest update

| Attribuut | Waarde |
|---|---|
| Actor | `AgentHealthMonitorAgent._check_all()` (background polling loop) |
| Voorwaarde | Status-transitie: `snap.status != prev_status` voor een agent in `_snapshots` |
| Actie | Scalaire waarden gekopieerd in lock; `await self._push_to_router(agent_id, status, success_rate, avg_latency_ms)` buiten lock |
| Systeemverwerking | `_push_to_router()` controleert tenant isolatie (`router.tenant_id == self.tenant_id`), roept `router.update_health_status()` aan; router acquireert `_manifests_lock` en werkt `AgentManifest.health_status`, `success_rate`, `avg_latency_ms` bij |
| Succesrespons | `manifest.health_status` bevat nieuwe status (bijv. "WARNING"); `HealthScorer.score_manifest()` retourneert lagere score; `_capability_match()` sortering benadeelt degraded agents correct |
| Foutrespons | Bij `Exception` in `_push_to_router()`: warning gelogd met `agent_id`; monitoring loop gaat door (best_effort patroon) |
| Uitzonderingen | Als `_router_ref is None`: geen actie (opt-in wiring); als `tenant_id` mismatch: silently return (tenant isolatie guard); als agent_id niet in router-manifests: early return |

### Flow 2: RedisRouteCacheTier -- cache-get met fallback

| Attribuut | Waarde |
|---|---|
| Actor | Caller die `RedisRouteCacheTier.get(cache_key, tenant_id)` aanroept |
| Voorwaarde | Redis-tier geconfigureerd, cache_key opgegeven |
| Actie | `await self._redis.get(f"route_cache:{tenant_id}:{cache_key}")` |
| Systeemverwerking | Redis GET; bij hit: JSON deserialize naar `RouteCacheEntry`; bij miss: None |
| Succesrespons | `RouteCacheEntry` teruggegeven (agent_id, agent_type, score) |
| Foutrespons | Bij `Exception` (Redis unavailable, JSON decode error): warning gelogd; `None` teruggegeven; caller valt door naar tier 2 |
| Uitzonderingen | Redis-tier is opt-in; als niet geconfigureerd: stap overgeslagen |

---

## Wiring in productie

De write-bridge is opt-in. Voor activatie in productie moet app_lifespan.py wiren:

```python
# In app startup (bijv. app_lifespan.py):
from src.core.agents.agent_router_agent import get_agent_router
from src.core.agents.agent_health_monitor_agent import get_health_monitor

router = get_agent_router(tenant_id=1)
monitor = get_health_monitor(tenant_id=1, router_ref=router)
```

Dit is bewust buiten scope van SP-WE-10 (app_lifespan.py wiring = apart ticket).

---

## Tests

| Test | Status |
|------|--------|
| `test_manifest_health_status_updated_on_transition` | PASS |
| `test_health_scorer_penalizes_critical_agent` | PASS |
| `test_redis_cache_tier_miss_falls_through` | PASS |
| `test_health_bridge_tenant_isolation` | PASS |
