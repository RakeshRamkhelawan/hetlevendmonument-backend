# BE-RTR-036 — Router Boundary Hardening (SP-API-010)

**Status:** IMPLEMENTED  
**Sprint:** SP-API-010  
**Datum:** 2026-06-12  
**ADR:** ADR-033 (Contract 1 uitbreiding)

---

## Samenvatting

DSM-audit 2026-06-12 toonde 14 verboden directe imports in 7 `router.py` bestanden die
buiten de bestaande import-linter Contract 1 scope vielen. Deze feature fixt alle 14
violations door:

1. Contract 1 `source_modules` uitgebreid met `src.core.api.auth.router`
2. Contract 1 `forbidden_modules` uitgebreid met `src.core.services`, `src.core.ml`,
   `src.core.als`, `src.core.semantic_router`
3. 7 `dependencies.py` bestanden aangemaakt of uitgebreid als ADR-033 facade (Laag 1)
4. Alle 14 verboden imports verplaatst van `router.py` naar de bijbehorende `dependencies.py`

---

## Violations voor de fix (14 totaal)

| Bestand | Violations | Module |
|---------|:----------:|--------|
| `auth/router.py` | 6 | `database.database`, `database.redis`, `database.tenant_query_filter`, `services.audit_service`, `services.email`, `services.rbac_service` |
| `v1/routing/router.py` | 2 | `als.enterprise.departments.department_orchestrator`, `semantic_router.embedders` |
| `v1/ml/router.py` | 1 | `ml.tool_predictor` |
| `v1/collaboration/router.py` | 1 | `services.collaboration_service` |
| `v1/gamification/router.py` | 1 | `services.gamification_service` |
| `v1/personas/router.py` | 1 | `services.persona_service` |
| `v1/tenant_custom_data/router.py` | 2 | `services.tenant_custom_data_repository`, `services.tenant_custom_data_service` |

---

## Implementatie

### Aangemaakt (nieuw)

- `src/core/api/v1/collaboration/dependencies.py` — re-export `UserPresence`, `get_collaboration_manager`
- `src/core/api/v1/ml/dependencies.py` — re-export `get_tool_predictor`
- `src/core/api/v1/routing/dependencies.py` — re-export `Department`, `OllamaEmbedder`
- `src/core/api/auth/dependencies.py` — re-export 6 items: `get_async_session`, `get_db`, `get_redis_client`, `TenantFilterBypass`, `SecurityEvent`, `log_security_event`, `send_password_reset_email`, `RBACService`

### Uitgebreid (bestaand)

- `src/core/api/v1/gamification/dependencies.py` — `GamificationService` toegevoegd
- `src/core/api/v1/personas/dependencies.py` — `get_db`, `PersonaService` toegevoegd
- `src/core/api/v1/tenant_custom_data/dependencies.py` — `TenantCustomDataRepository`, `TenantCustomDataService` toegevoegd

### Gewijzigd (routers)

- `src/core/api/auth/router.py` — 6 imports naar `.dependencies`
- `src/core/api/v1/collaboration/router.py` — 1 import naar `.dependencies`
- `src/core/api/v1/gamification/router.py` — 1 import naar `.dependencies`
- `src/core/api/v1/ml/router.py` — 1 import naar `.dependencies`
- `src/core/api/v1/personas/router.py` — 2 imports naar `.dependencies`
- `src/core/api/v1/routing/router.py` — deferred `OllamaEmbedder` import verwijderd (was unused), `Department` naar module-level via `.dependencies`
- `src/core/api/v1/tenant_custom_data/router.py` — 2 imports naar `.dependencies`

### Config

- `.importlinter` — `source_modules`, `forbidden_modules`, `ignore_imports` uitgebreid

---

## Testen

- `tests/unit/test_sp_api_010_router_boundary.py` — 13 tests, alle GROEN
- Architecture tests: 106 passed, 12 xfailed
- Import-linter: 4 contracts KEPT, 0 broken (1 warning: ml.dependencies edge niet in graph)
- Pyright op gewijzigde bestanden: 0 errors

---

## Bekende beperkingen

- `routing/router.py` heeft `# orphan:exempt` marker — pending Strangler Fig migratie
- Import-linter warning voor `ml.dependencies -> ml.tool_predictor`: statisch analyse kan
  edge niet tracen omdat `sklearn`/`joblib` niet in analyse-venv zitten; edge bestaat wel
- 2 pre-existing pyright errors in `crag_endpoints.py` en `pack_intent_matcher.py` (niet
  veroorzaakt door deze sprint — bestonden al na SP-AGT-004)

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
