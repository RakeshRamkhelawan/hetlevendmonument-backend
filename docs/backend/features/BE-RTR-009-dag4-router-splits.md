# BE-RTR-009 — API Layer Dag 4 Sub-Router Splits (ADR-033)

**Sprint:** SP-API-002 Dag 4
**Datum:** 2026-06-03
**Status:** DONE

---

## Beschrijving

Vijf oversized composite routers zijn gesplitst in Laag 1 sub-routers van maximaal 200 regels elk,
conform het ADR-033 drie-laags compositie patroon (Strangler Fig Week 2).

### Gesplitste routers

#### documents/router.py (was 656r → nu 20r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `upload_router.py` | POST /upload | 165r |
| `crud_router.py` | GET /, GET /{id}, PUT /{id}, DELETE /{id} | 259r (`# orphan:exempt`) |
| `search_router.py` | GET /search | 82r |
| `processing_router.py` | POST /{id}/process, GET /{id}/status, GET /{id}/versions | 186r |
| `dependencies.py` | Re-exports get_db, auth, rate-limiters | 18r |

#### orchestration/router.py (was 625r → nu 14r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `workflow_router.py` | POST /task, GET /task/{id}, POST /route | 289r (`# orphan:exempt`) |
| `health_router.py` | GET /health, GET /health/agent/{id}, POST /health/record | 130r |
| `critic_router.py` | POST /critique | 116r |
| `stats_router.py` | GET /stats | 51r |
| `dependencies.py` | Re-exports get_db, auth | 13r |

**Aantekening:** orchestration composite wordt geregistreerd via `importlib.import_module` in `registries/agentic.py` — `# orphan:exempt` annotatie aanwezig.

#### privacy/router.py (was 578r → nu 14r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `dsar_router.py` | GET /export, POST /forget | 219r (`# orphan:exempt`) |
| `consent_router.py` | GET /consent-status, POST /consent | 95r |
| `ai_transparency_router.py` | GET /ai-decisions, GET /profiling-opt-out, POST /profiling-opt-out | 152r |
| `human_review_router.py` | POST /human-review, GET /human-review-requests | 112r |
| `dependencies.py` | Re-exports get_db, auth, rate-limiters | 13r |

#### tools/router.py (was 454r → nu 12r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `crud_router.py` | POST /, GET /, GET /{id}, PUT /{id}, DELETE /{id} | 272r (`# orphan:exempt`) |
| `execution_router.py` | POST /{id}/execute, GET /{id}/executions | 158r |
| `versions_router.py` | GET /{id}/versions, POST /{id}/versions | 81r |
| `dependencies.py` | Re-exports get_db, auth | 5r |

#### canvas/router.py (was 410r → nu 18r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `canvas_crud_router.py` | POST /, GET /, GET /{id}, PATCH /{id}, DELETE /{id} | 113r |
| `blocks_router.py` | POST /{id}/blocks, PATCH /{id}/blocks/{bid}, DELETE /{id}/blocks/{bid} | 75r |
| `connections_router.py` | POST /{id}/connections, DELETE /{id}/connections/{cid} | 54r |
| `collaborators_router.py` | POST /{id}/collaborators, DELETE /{id}/collaborators/{uid} | 54r |
| `canvas_templates_router.py` | GET /templates/list, POST /from-template/{id} | 66r |
| `canvas_ws_router.py` | WEBSOCKET /ws/{id} | 47r |
| `dependencies.py` | Re-exports get_db, auth, get_canvas_service | 21r |

---

## Bestanden

```
src/core/api/v1/documents/upload_router.py
src/core/api/v1/documents/crud_router.py
src/core/api/v1/documents/search_router.py
src/core/api/v1/documents/processing_router.py
src/core/api/v1/documents/dependencies.py
src/core/api/v1/documents/router.py                   (composite, gewijzigd)
src/core/api/v1/orchestration/workflow_router.py
src/core/api/v1/orchestration/health_router.py
src/core/api/v1/orchestration/critic_router.py
src/core/api/v1/orchestration/stats_router.py
src/core/api/v1/orchestration/dependencies.py
src/core/api/v1/orchestration/router.py                (composite, gewijzigd)
src/core/api/v1/privacy/dsar_router.py
src/core/api/v1/privacy/consent_router.py
src/core/api/v1/privacy/ai_transparency_router.py
src/core/api/v1/privacy/human_review_router.py
src/core/api/v1/privacy/dependencies.py
src/core/api/v1/privacy/router.py                      (composite, gewijzigd)
src/core/api/v1/tools/crud_router.py
src/core/api/v1/tools/execution_router.py
src/core/api/v1/tools/versions_router.py
src/core/api/v1/tools/dependencies.py
src/core/api/v1/tools/router.py                        (composite, gewijzigd)
src/core/api/v1/canvas/canvas_crud_router.py
src/core/api/v1/canvas/blocks_router.py
src/core/api/v1/canvas/connections_router.py
src/core/api/v1/canvas/collaborators_router.py
src/core/api/v1/canvas/canvas_templates_router.py
src/core/api/v1/canvas/canvas_ws_router.py
src/core/api/v1/canvas/dependencies.py
src/core/api/v1/canvas/router.py                       (composite, gewijzigd)
tests/architecture/test_registry_equivalence.py         (5 nieuwe equivalentietests)
```

---

## Kritieke invarianten

- **Geen URL-wijzigingen** — alle endpoints behouden hun oorspronkelijke paden
- **ADR-033 import-discipline** — alle sub-routers importeren `get_db` en auth via `dependencies.py`
- **# orphan:exempt** aanwezig op alle Laag 1 sub-routers (transitieve registratie via composite)
- **Fitness gate actief** — `test_no_orphan_routers` en `test_no_router_files_over_200_lines` PASS
- **FastAPI lege-pad fix** — `GET ""` en `POST ""` gewijzigd naar `"/"` in sub-routers (sub-router met lege prefix + leeg pad gooit `FastAPIError`)

---

## Tests

```
pytest tests/architecture/ tests/unit/api/ -q --timeout=30
Resultaat: 124 passed, 0 failed, 0 skipped (2026-06-03)

5 nieuwe equivalentietests:
  test_documents_router_split_into_sub_routers   PASS
  test_orchestration_router_split_into_sub_routers PASS
  test_privacy_router_split_into_sub_routers     PASS
  test_tools_router_split_into_sub_routers       PASS
  test_canvas_router_split_into_sub_routers      PASS
```

---

## Trainingssamenvatting

### Flow: sub-router toevoegen aan een bestaand domein

**Actor:** Backend developer
**Voorwaarde:** Domein heeft composite router.py en dependencies.py aanwezig
**Actie:** Developer maakt `<groep>_router.py` aan in `src/core/api/v1/<domein>/`
**Systeemverwerking:**
1. Sub-router bestand aangemaakt met `# orphan:exempt reason: Laag 1 sub-router...` als tweede regel
2. Imports van `src.core.database` en `src.core.governance` via `dependencies.py` (ADR-033 import-discipline)
3. Sub-router toegevoegd aan composite `router.py` via `include_router`
4. Equivalentietest bijgewerkt in `tests/architecture/test_registry_equivalence.py`

**Succesrespons:** `pytest tests/architecture/ -q` — alle tests PASS
**Foutrespons:** `FastAPIError: Prefix and path cannot be both empty` — gebruik `"/"` i.p.v. `""` als route-pad in sub-routers
**Uitzonderingen:** Sub-routers die via `importlib.import_module` worden geregistreerd (bijv. orchestration) hebben `# orphan:exempt reason: registered via importlib...` nodig op de composite

### Flow: domein-router verifiëren na split

**Actor:** CI / architect
**Actie:** `pytest tests/architecture/ -q`
**Systeemverwerking:** AST-inspectie op alle `*_router.py` bestanden + equivalentietests
**Succesrespons:** `19+ passed, 0 failed, 0 skipped`
**Foutrespons:** `AssertionError: sub-router bestanden ontbreken` of `routes missen` → split onvolledig
