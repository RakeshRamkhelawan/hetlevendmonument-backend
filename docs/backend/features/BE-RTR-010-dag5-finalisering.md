# BE-RTR-010 — API Layer Dag 5 Finalisering (ADR-033)

**Sprint:** SP-API-002 Dag 5
**Datum:** 2026-06-03
**Status:** DONE

---

## Beschrijving

SP-API-002 Dag 5 voltooit de Strangler Fig migratie. Drie resterende routers zijn gesplitst,
4 mypy-fouten zijn gefixed, en de sprint is administratief afgesloten.

### Taak 1 — Mypy-fixes (eerste taak)

| Fix | Bestand | Probleem | Oplossing |
|---|---|---|---|
| M-001 | `documents/upload_router.py:11` | `Library stubs not installed for "aiofiles"` | `# type: ignore[import-untyped]` |
| M-002 | `orchestration/stats_router.py:19` | `Module "workflow_router" has no attribute "get_health_monitor"` | Import verplaatst naar `health_router.py` |
| M-003 | `orchestration/stats_router.py:21` | `Unused "type: ignore"` | Stale comment verwijderd na M-002 fix |
| M-004 | `orchestration/workflow_router.py:58` | `No parameter named "critic"` | Pre-existing bug gefixed in Dag 4 |

### Taak 2 — Gesplitste routers

#### tenants/router.py (was 315r → nu 11r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `tenants_list_router.py` | POST /, GET / | ~105r |
| `tenants_detail_router.py` | GET /{id}, PUT /{id}, DELETE /{id} | ~120r |
| `tenants_stats_router.py` | GET /{id}/stats | ~75r |
| `dependencies.py` | Re-exports get_db, get_current_user | ~6r |

#### als/router.py (was 288r → nu 14r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `shared.py` | Schemas (TaskRequest, TaskResponse, HealthResponse) + get_orchestrator | ~50r |
| `als_tasks_router.py` | POST /tasks, POST /broadcast | ~105r |
| `als_health_router.py` | GET /health | ~28r |
| `als_agents_router.py` | GET /agents, POST /agents/{id}/ping, GET /agents/{id}/heartbeat | ~100r |

**Aantekening:** als/router.py composite heeft `# orphan:exempt reason: registered via importlib.import_module`.

#### agentic/router.py (was 267r → nu 22r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `agentic_routing_router.py` | POST /route | ~50r |
| `agentic_domain_router.py` | POST /finance/decompose, POST /packs/execute, POST /feedback | ~130r |
| `agentic_roi_router.py` | GET /roi/supervisor/{id}, GET /roi/dashboard, GET /health | ~65r |

**Aantekening:** agentic/router.py composite behoudt 5 pre-existing sub-module includes
(agents, agent_discovery, router_debug, learning, monitoring).

---

## Bestanden

```
src/core/api/v1/tenants/tenants_list_router.py
src/core/api/v1/tenants/tenants_detail_router.py
src/core/api/v1/tenants/tenants_stats_router.py
src/core/api/v1/tenants/dependencies.py
src/core/api/v1/tenants/router.py               (composite, gewijzigd)
src/core/api/v1/als/shared.py
src/core/api/v1/als/als_tasks_router.py
src/core/api/v1/als/als_health_router.py
src/core/api/v1/als/als_agents_router.py
src/core/api/v1/als/router.py                    (composite, gewijzigd)
src/core/api/v1/agentic/agentic_routing_router.py
src/core/api/v1/agentic/agentic_domain_router.py
src/core/api/v1/agentic/agentic_roi_router.py
src/core/api/v1/agentic/router.py                (composite, gewijzigd)
src/core/api/v1/documents/upload_router.py        (mypy fix)
src/core/api/v1/orchestration/stats_router.py     (mypy fix)
tests/architecture/test_registry_equivalence.py   (3 nieuwe equivalentietests)
CLAUDE.md                                          (SP-API-002 toegevoegd)
```

---

## Tests

```
pytest tests/architecture/ tests/unit/api/ -q --timeout=30
Resultaat: 127 passed, 0 failed, 0 skipped (2026-06-03)

3 nieuwe equivalentietests:
  test_tenants_router_split_into_sub_routers   PASS
  test_als_router_split_into_sub_routers       PASS
  test_agentic_router_split_into_sub_routers   PASS
```

---

## Sprint SP-API-002 eindstand

| Metriek | Voor (Week 1 einde) | Na (Week 2 einde) |
|---|---|---|
| Oversized v1/router.py bestanden | 11 | 0 (alle <=200r of orphan:exempt) |
| Fitness gate tests | 2 SKIP | 0 SKIP, alle PASS |
| Architecture tests totaal | 14 PASS, 2 SKIP | 27 PASS, 0 SKIP |
| Unit/api tests | 94 PASS | 100 PASS |
| Totaal tests | 108 | 127 |

---

## Trainingssamenvatting

### Flow: sub-router met importlib-geregistreerde composite

**Actor:** Backend developer
**Voorwaarde:** Domein wordt geregistreerd via `importlib.import_module` (niet via static import)
**Actie:** Developer maakt composite router.py aan voor het domein
**Systeemverwerking:**
1. Composite router.py aangemaakt met sub-router includes
2. `# orphan:exempt reason: registered via importlib.import_module in registries/<naam>.py` toegevoegd
3. `test_no_orphan_routers` PASS

**Succesrespons:** Fitness gate slaagt, geen orphan-waarschuwingen
**Foutrespons:** `AssertionError: Orphan router-bestanden gevonden` → orphan:exempt ontbreekt
**Uitzonderingen:** Alleen nodig voor domeinen die via `importlib.import_module` string-geregistreerd zijn (als, orchestration)

### Flow: mypy stubs-fout bij nieuwe import

**Actor:** CI / developer
**Actie:** Nieuw bestand importeert library zonder type stubs (bijv. `aiofiles`)
**Systeemverwerking:** mypy rapporteert `Library stubs not installed for "X"`
**Succesrespons:** `# type: ignore[import-untyped]` toegevoegd aan import-regel
**Foutrespons:** Mypy-error blijft → controleer of `types-X` package beschikbaar is
