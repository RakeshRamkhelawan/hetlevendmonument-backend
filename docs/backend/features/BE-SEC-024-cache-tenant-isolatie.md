# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-024
- Feature naam: Cache-sleutels tenant-isolatie (TI-001..005)
- Status: DONE
- Auteur: Uitvoerende agent SP-SEC-001 Dag 1
- Reviewer: Zie docs/backend/review/review-BE-SEC-024.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: SP-SEC-001 TI-001..005 (multidisciplinaire audit 2026-06-30)
- Gerelateerde router / module: cache_layer, embedding_service, performance_middleware, intelligent_router, goal_service
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

Vijf cache-sleutels bevatten geen tenant_id prefix, waardoor cached responses van tenant A
door tenant B gelezen kunnen worden. Fix: elke cache-sleutel krijgt prefix `t{_tid}:` waarbij
`_tid = get_tenant_id() or 0` (of `self._tenant.tenant_id or 0` voor GoalService).
`t0` = system namespace; nooit een echte tenant (tenant_id > 0 per ADR-005).

### In scope

- `src/core/caching/cache_layer.py` (TI-001): `cached()` decorator cache-sleutel
- `src/core/knowledge/embedding_service.py` (TI-002): `generate_embedding()` cache-sleutel
- `src/core/api/performance_middleware.py` (TI-003): `cached_response()` decorator cache-sleutel
- `src/core/llm/intelligent_router.py` (TI-004): `select_provider()` cache-sleutel
- `src/core/company/goal_service.py` (TI-005): `get_ancestry()` + `_invalidate_ancestry_cache()` cache-sleutels
- 5 unit tests + 1 architecture test (CI-blokkering voor herhaling)

### Out of scope

- BP-001 sweep (248 endpoints -- deferred naar SP-SEC-002)
- Invalidatie-logica buiten de genoemde methoden
- Redis TTL-waarden aanpassen

---

## Build summary

- Nieuw gebouwd: 5 unit tests, 1 architecture test, `tests/unit/caching/__init__.py`
- Gewijzigd: 5 bronbestanden (cache_layer.py, embedding_service.py, performance_middleware.py, intelligent_router.py, goal_service.py)
- Verwijderd: --
- Beinvloede bestaande flows: alle cached service-aanroepen; cache-sleutels zijn nu tenant-gescheiden

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-024-TI-001 | cached() decorator tenant prefix | BE-UTL | src/core/caching/cache_layer.py | Wijziging | Elke gecachede service-aanroep |
| BE-SEC-024-TI-002 | generate_embedding() tenant prefix | BE-SVC | src/core/knowledge/embedding_service.py | Wijziging | Embedding generatie |
| BE-SEC-024-TI-003 | cached_response() decorator tenant prefix | BE-MID | src/core/api/performance_middleware.py | Wijziging | API response caching |
| BE-SEC-024-TI-004 | select_provider() tenant prefix | BE-SVC | src/core/llm/intelligent_router.py | Wijziging | LLM provider selectie |
| BE-SEC-024-TI-005 | get_ancestry() + invalidate tenant prefix | BE-SVC | src/core/company/goal_service.py | Wijziging | Goal ancestry ophalen |

---

## API-flows

### Flow BE-FLW-SEC-024

- Naam: Tenant-gevalideerde cache lookup
- Trigger: elke aanroep van een gecachede service-methode
- Voorwaarden: TenantMiddleware heeft `_tenant_context` ContextVar gezet (of GoalService heeft `self._tenant.tenant_id`)
- Request-pad: gecachede methode aangeroepen
- Service-stappen: 1) `_tid = get_tenant_id() or 0`, 2) `cache_key = f"t{_tid}:..."`, 3) cache lookup
- DB-operaties: --
- Successtatus: cache hit of miss -- functie geeft resultaat terug
- Foutpaden: `get_tenant_id()` retourneert `None` -> `_tid = 0` (system namespace, veilig)
- Eindtoestand: cache-entry getagged met tenant_id; cross-tenant lekken onmogelijk

---

## Detaildocumentatie per artefact

---

## [BE-SEC-024-TI-001] cached() decorator -- cache_layer.py

### 1. Type

- Utility / decorator

### 2. Locatie

- Bestandspad: src/core/caching/cache_layer.py
- Functie: `cached()` (decorator, inner `async_wrapper`)

### 4. Doel

Elke gecachede functie-aanroep slaat resultaten op met een tenant-gescopede sleutel zodat
resultaten van tenant A nooit zichtbaar zijn voor tenant B.

### 5. Functionele beschrijving

- De `cached()` decorator wrapt asynchrone functies met een Redis/in-memory cache-laag.
- Sleutel bevat nu: `t{tenant_id}:{key_prefix}:{func.__name__}:{md5(args+kwargs)}`
- Tenant_id wordt gelezen via `get_tenant_id()` uit de ContextVar (gezet door TenantMiddleware).
- Fallback `or 0`: als er geen tenant context is (systeem-aanroep), wordt t0 gebruikt.
- hashlib.md5() (niet Python hash()) voor cross-process stabiliteit met Gunicorn workers.

### 6. Technische beschrijving

```python
_tid = get_tenant_id() or 0
_arg_hash = hashlib.md5(
    (arg_str + kwarg_str).encode(), usedforsecurity=False
).hexdigest()
cache_key = f"t{_tid}:{key_prefix}:{func.__name__}:{_arg_hash}"
```

### 16. Caching

- Cache-sleutel: `t{tenant_id}:{key_prefix}:{func.__name__}:{md5(args+kwargs)}`
- TTL: door decorator-caller geconfigureerd
- Invalidatie: TTL-based; geen expliciete invalidatie in cache_layer

### 17. Acceptatiecriteria

- Cache-sleutel voor tenant 1 != sleutel voor tenant 2 bij identieke args (unit test GROEN)
- `t0` wordt gebruikt wanneer `get_tenant_id()` `None` retourneert
- Architecture test `test_all_cache_keys_contain_tenant_id` GROEN

### 19. Trainingssamenvatting

- Actor: gecachede service-methode
- Voorwaarde: TenantMiddleware heeft ContextVar gezet
- Actie: service-methode aangeroepen met args
- Systeemverwerking: cache_key gebouwd met `t{_tid}:` prefix; cache lookup
- Succesrespons: gecachte waarde of verse waarde opgeslagen onder tenant-gescopede sleutel
- Foutrespons: geen; fallback naar t0 bij ontbrekende tenant context
- Uitzonderingen: GoalService gebruikt `self._tenant.tenant_id` (niet ContextVar) -- zie TI-005

---

## [BE-SEC-024-TI-005] GoalService ancestry cache -- goal_service.py

### 1. Type

- Service

### 2. Locatie

- Bestandspad: src/core/company/goal_service.py
- Klasse / functie: `GoalService.get_ancestry()` + `GoalService._invalidate_ancestry_cache()`

### 4. Doel

Goal ancestry resultaten worden gecachet in Redis. Sleutels waren niet tenant-gescopeed.
Fix: `self._tenant.tenant_id` (geinjected context, niet ContextVar) als prefix.

### 5. Functionele beschrijving

- `get_ancestry()` haalt de hiearchische keten van een goal op, gecachet voor 5 minuten.
- `_invalidate_ancestry_cache()` verwijdert de cache-entry na een update.
- Beide methoden gebruiken nu `t{self._tenant.tenant_id or 0}:ancestry_cache:{goal_id}`.

### 6. Technische beschrijving

```python
_tid = self._tenant.tenant_id or 0
cache_key = f"t{_tid}:{self.ANCESTRY_CACHE_PREFIX}:{goal_id}"
```

Keuze voor `self._tenant.tenant_id` (niet `get_tenant_id()`): GoalService heeft al een
geinjected `TenantContext` object -- directe toegang voorkomt dat `_tid = 0` optreedt
wanneer de ContextVar nog niet gezet is (QR-011 review finding).

### 16. Caching

- Cache-sleutel: `t{tenant_id}:ancestry_cache:{goal_id}`
- TTL: `ANCESTRY_CACHE_TTL = 300` seconden
- Invalidatie: bij `update_progress()` roept `_invalidate_ancestry_cache(goal_id)` aan

### 17. Acceptatiecriteria

- Redis.get() sleutels voor tenant 1 != sleutels voor tenant 2 (unit test GROEN)
- Invalidatie gebruikt dezelfde tenant-gescopede sleutel

### 19. Trainingssamenvatting

- Actor: GoalService
- Voorwaarde: GoalService geinstantieerd met TenantContext
- Actie: `get_ancestry(goal_id)` aangeroepen
- Systeemverwerking: cache-sleutel `t{tenant_id}:ancestry_cache:{goal_id}` gebouwd; Redis lookup
- Succesrespons: GoalAncestryResponse uit cache of database
- Foutrespons: geen; Redis-fouten vallen terug op directe DB-query
- Uitzonderingen: `self._tenant.tenant_id = None` -> `_tid = 0` (system namespace)

---

## QA-checks

- [x] Tenant-isolatie getest (5 unit tests GROEN)
- [x] Architecture test als CI-blokkering GROEN
- [x] Pyright 0 errors na wijzigingen
- [x] MD5 usedforsecurity=False (bandit compliant)

---

## Definition of Done

- [x] Feature is gebouwd (5 bronbestanden gefixed)
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Trainingssamenvatting aanwezig
- [x] Review: zie review-BE-SEC-024.md
