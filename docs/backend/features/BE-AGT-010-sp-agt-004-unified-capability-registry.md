# BE-AGT-010 -- UnifiedCapabilityRegistry Skeleton

**Sprint:** SP-AGT-004 Dag 1
**Datum:** 2026-06-12
**Status:** APPROVED
**ADR:** ADR-027 §12, ADR-034 §5.5

---

## Samenvatting

In-memory implementatie van `UnifiedCapabilityRegistry` als authoritative registry
voor capability discovery. Dag 1 scope: skeleton + Protocol binding. Persistentie
volgt in Dag 2+.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/capability_registry.py` | Nieuw -- UnifiedCapabilityRegistry |
| `tests/unit/agents/test_unified_capability_registry.py` | Nieuw -- 5 unit tests |
| `tests/architecture/test_sp_agt_004_ucr_wiring.py` | Nieuw -- 5 arch tests |

---

## Ontwerp

### UnifiedCapabilityRegistry

```
UnifiedCapabilityRegistry
  _store: dict[tenant_id, list[AgentCapability]]   -- in-memory, per-tenant
  _register(tenant_id, capability)                 -- interne setup (test/seed)
  discover(query, tenant_id) -> list[AgentCapability]  -- ICapabilityRegistry interface
```

### Protocol binding

Implementeert `ICapabilityRegistry` uit `src/core/agents/api.py`:
```python
@runtime_checkable
class ICapabilityRegistry(Protocol):
    async def discover(self, query: str, tenant_id: int) -> list[AgentCapability]: ...
```

`isinstance(ucr, ICapabilityRegistry)` geeft `True` (runtime_checkable).

### Tenant-isolatie

`_store` is geindexeerd op `tenant_id`. `discover()` leest uitsluitend
`self._store[tenant_id]` -- tenant A kan nooit capabilities van tenant B zien.

### Kopie-bescherming

`discover()` retourneert `list(caps)` -- een nieuwe lijst. Mutaties op de
returnwaarde beinvloeden de interne state niet.

### Geen directe DB-import

`capability_registry.py` importeert `src.core.database` niet (ADR-034 verbiedt dit).

---

## Tests

| Test | Doel |
|------|------|
| `test_ucr_implements_icapability_registry_protocol` | Protocol-contract |
| `test_ucr_discover_empty_query_returns_all` | Happy path -- leeg query |
| `test_ucr_discover_filters_by_name` | Happy path -- query-filter |
| `test_ucr_discover_isolates_tenants` | Security -- tenant-isolatie |
| `test_ucr_discover_returns_copy_not_reference` | Security -- geen state-lek |

Alle 5 tests: RED voor implementatie, GREEN na implementatie.

---

## Dag 2: ICacheBackend + Redis-adapter (SP-AGT-004)

**Datum:** 2026-06-12

### Wijzigingen

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/api.py` | `ICacheBackend` Protocol + `register_agent` aan `ICapabilityRegistry` |
| `src/core/agents/capability_registry.py` | Constructor-injectie cache; `register_agent()`; lazy-load; `_loaded` guard |
| `src/core/agents/adapters/__init__.py` | Nieuw subpackage |
| `src/core/agents/adapters/redis_capability_cache.py` | `RedisCapabilityCache` -- concrete `ICacheBackend` |
| `tests/unit/agents/test_unified_capability_registry.py` | 5 nieuwe tests (test_1_6 t/m test_1_10) |

### Ontwerp Dag 2

```
UnifiedCapabilityRegistry(cache: ICacheBackend | None = None)
  _store: dict[int, list[AgentCapability]]   -- L1 in-memory
  _loaded: set[int]                          -- tenants waarvan Redis geladen is
  register_agent(tenant_id, capability)      -- publiek async; L1 + L2 write-through
  discover(query, tenant_id)                 -- lazy-load L2 bij memory miss
  _load_from_cache(tenant_id)                -- Redis -> L1; fouten via best_effort
  _redis_key(tenant_id, capability) -> str   -- staticmethod: "ucr:{tid}:{name}"

ICacheBackend (Protocol in api.py):
  set(key, value, ttl) / get(key) / keys(pattern)

RedisCapabilityCache (adapters/):
  Enige plek in src.core.agents die src.core.database mag importeren
```

### Boundary-garantie

`capability_registry.py` importeert geen `src.core.database` (architecture test bewaakt dit).
`RedisCapabilityCache` in `adapters/` is de enige toegestane doorgang.

### Tests Dag 2

| Test | Doel |
|------|------|
| `test_ucr_register_agent_public_stores_in_memory` | Happy path -- in-memory opslag |
| `test_ucr_register_agent_writes_to_cache` | Write-through naar `ICacheBackend.set()` |
| `test_ucr_discover_lazy_loads_from_cache_on_memory_miss` | Lazy-load bij miss |
| `test_ucr_register_agent_cache_failure_does_not_raise` | Resilience -- cache-fout op write |
| `test_ucr_discover_cache_failure_returns_empty_gracefully` | Resilience -- cache-fout op load |

Totaal: 15 tests GREEN (10 Dag 1 + 5 Dag 2).

---

## Dag 3: Agent event-bus + lifespan wiring (SP-AGT-004)

**Datum:** 2026-06-12

### Wijzigingen

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/adapters/redis_capability_cache.py` | FA-002 fix: KEYS -> scan_iter (O(scan), non-blocking) |
| `src/core/shared/events/__init__.py` | Nieuw package |
| `src/core/shared/events/agent_events.py` | IEventBus Protocol + 3 typed events |
| `src/core/app_lifespan.py` | `_init_ucr()` helper + init_steps wiring |
| `tests/unit/agents/test_unified_capability_registry.py` | FA-004: mock_cache.keys.assert_not_called() toegevoegd |
| `tests/unit/agents/test_agent_events.py` | Nieuw: 3 tests |
| `tests/architecture/test_sp_agt_004_ucr_wiring.py` | test_ucr_constructable_with_redis_cache toegevoegd |
| `tests/architecture/test_sp_agt_004_ucr_partial_load.py` | FA-003 backlog: intentioneel rode test |

### DSM governance baseline

Governance imports in `src/core/agents`: **4 bestanden, 5 regels** (doel Dag 4: < 5 regels).

### Agent event-bus Protocol

```
IEventBus (Protocol):
  publish(event: AgentEvent) -> None

AgentEvent (base, frozen dataclass):
  tenant_id: int
  occurred_at: datetime  # always timezone.utc

AgentCapabilityRegistered / AgentExecutionRequested / AgentExecutionCompleted
```

Governance-decoupling via event-bus: agents publiceren events, governance abonneert zich.
Directe `src.core.governance` imports worden daarmee overbodig (Dag 4/5 scope).

### Lifespan wiring

`app.state.ucr` = `UnifiedCapabilityRegistry(cache=RedisCapabilityCache())` bij startup.
Non-fatal: als Redis unavailable is, start de app zonder UCR cache (in-memory fallback actief).

### Tests Dag 3

| Test | Doel |
|------|------|
| `test_agent_events_module_importable` | Module importeerbaar |
| `test_agent_capability_registered_event_has_required_fields` | Event velden correct |
| `test_ievent_bus_protocol_has_publish_method` | Protocol heeft publish |
| `test_ucr_constructable_with_redis_cache` | UCR+cache constructie geen exception |
| `test_ucr_loaded_guard_resets_on_partial_cache_failure` | FA-003 backlog (intentioneel ROOD) |

Totaal groen: 19 tests (15 Dag 1+2 + 4 Dag 3); 1 intentioneel rood (FA-003 backlog).

---

## Dag 4: FA-003 partial-load reset + minors (SP-AGT-004)

**Datum:** 2026-06-12

### Wijzigingen

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/capability_registry.py` | FA-003: `_load_from_cache` retourneert `bool`; `discover()` doet `_loaded.discard(tenant_id)` bij False |
| `src/core/agents/adapters/redis_capability_cache.py` | FA-D3-001: `str(key)` verwijderd -- `decode_responses=True` garandeert al `str` |
| `tests/architecture/test_sp_agt_004_ucr_partial_load.py` | FA-D3-002: `@pytest.mark.unit` + xfail vervangen door 2 echte gedragstests |
| `src/core/app_lifespan.py` | FA-D3-004: `except Exception` versmald naar `(ImportError, OSError, ValueError, AttributeError)` |
| `src/core/agents/agent_registry.py` | Governance: soft try/except import `OversightGate` verwijderd; `GOVERNANCE_AVAILABLE` vlag geëlimineerd; `oversight_gate: Any | None` |

### Governance baseline na Dag 4

Governance imports in `src/core/agents`: **3 bestanden, 4 regels** (was: 4 bestanden, 5 regels).

### Tests Dag 4

| Test | Doel | Status |
|------|------|--------|
| `test_ucr_loaded_guard_resets_on_partial_cache_failure` | FA-003: `_loaded` niet gezet na cache-fout | PASSED |
| `test_ucr_second_discover_retries_after_load_failure` | FA-003: tweede discover herprobeert na reset | PASSED |

Totaal: 2 nieuwe tests GROEN + alle 21 eerdere tests intact.

---

## Openstaand (Dag 5 scope)

- AgentRouterAgent Tier-3 integratie (ADR-027 s12)
- Contract 3 import-linter uitbreiding (vereist GO Rakesh)
- Categorie B database violations (ADR-034 s11)
- FA-D3-003: relatieve `Path("src/...")` in architecture tests (pre-existing)

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
