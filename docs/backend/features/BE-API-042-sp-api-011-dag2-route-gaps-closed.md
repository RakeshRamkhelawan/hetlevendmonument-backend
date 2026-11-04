# BE-API-042: SP-API-011 Dag 2 -- Ontbrekende v1/ routes + clear_tenant_cache caller (6 xfails -> 0)

## Samenvatting

SP-API-011 Dag 2: zes openstaande arch-test xfails gesloten door een `clear_tenant_cache`
caller toe te voegen en vijf ontbrekende v1/ stub-routes aan te maken.

## Wijzigingen

### 2a. clear_tenant_cache caller in delete_tenant (1 xfail gesloten)

**Bestanden:**
- `src/core/api/v1/tenants/dependencies.py` -- re-export `clear_tenant_cache` uit orchestration/dependencies
- `src/core/api/v1/tenants/tenants_detail_router.py` -- caller toegevoegd in `delete_tenant()`

**Beslissing:** per ADR-033 patroon gaat de cross-domain re-export via `tenants/dependencies.py`.
De call staat na `db.commit()`: primaire data (tenant deactivatie) wordt eerst gesaved.
Agent-cache-evictie is best-effort; als het mislukt heeft de tenant al de juiste status in de DB.

```python
# tenants/dependencies.py
from src.core.api.v1.orchestration.dependencies import clear_tenant_cache as clear_tenant_cache

# tenants_detail_router.py -- in delete_tenant()
await db.commit()
clear_tenant_cache(tenant_id)
```

### 2b/2c. GET /integrations/catalog + GET /integrations/search (2 xfails gesloten)

**Nieuw bestand:** `src/core/api/v1/tools/integrations_router.py`

Twee stub GET-routes met auth guard (`require_authenticated_user`) en verplichte
`limit`/`offset` query parameters per backend-patterns.md §5.

Geregistreerd in `src/core/api/v1/tools/router.py` via `router.include_router(integrations_router)`.

### 2d. WebSocket /ws/builder alias (1 xfail gesloten)

**Bestand:** `src/core/api/v1/agentic/websocket.py`

Route `@router.websocket("/ws/builder")` toegevoegd. Doet `accept()` gevolgd door `close(1001,
reason="Moved to /ws/agent/stream")`. Frontend kan migreren naar `/ws/agent/stream`.

### 2e/2f. POST /{template_id}/deploy + GET /search/ in template_router.py (2 xfails gesloten)

**Bestand:** `src/core/api/v1/company/template_router.py`

Beide routes geregistreerd VOOR `GET /{template_id}` om routing-conflicts te voorkomen
(literal paden hebben voorrang op UUID-parameters). Stubs retourneren correcte HTTP-statuscodes
(202 Accepted voor deploy, 200 voor search).

## Gewijzigde bestanden

**Broncode (6 bestanden):**
- `src/core/api/v1/tenants/dependencies.py` (clear_tenant_cache re-export)
- `src/core/api/v1/tenants/tenants_detail_router.py` (caller in delete_tenant)
- `src/core/api/v1/tools/integrations_router.py` (nieuw -- 2 stub GET routes)
- `src/core/api/v1/tools/router.py` (integrations_router included)
- `src/core/api/v1/agentic/websocket.py` (/ws/builder alias)
- `src/core/api/v1/company/template_router.py` (/search/ + /{id}/deploy routes)

**Tests (2 bestanden):**
- `tests/architecture/test_flat_file_migration_gaps.py` (5 xfail markers verwijderd, pytest import opgeruimd)
- `tests/architecture/test_sp_api_010_backlog.py` (clear_tenant_cache xfail marker verwijderd)

## Verificatie

```
Architecture tests: 291 passed, 0 failed, 3 xfailed (was 285/0/9)
Targeted unit tests: 773 passed, 0 failed
pyright: 0 errors, 57 warnings (baseline gehandhaafd)
```

## DoD

- [x] Alle deliverables op verwachte paden
- [x] Architecture tests: xfail 9 -> 3 (Dag 2 target)
- [x] pyright 0 errors
- [x] Geen regressies in gerichte tests (773 passed)
- [x] Feature spec aangemaakt
- [x] ID-REGISTRY bijgewerkt


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-API-011 Dag 2: 6 xfails gesloten. clear_tenant_cache() caller in delete_tenant (re-export via tenants/dependencies.py). GET /integrations/catalog + GET /integrations/search stubs in tools/integrations_router.py. WebSocket /ws/builder alias (accept+close 1001). POST /{template_id}/deploy + GET /search/ in template_router.py (voor /{template_id} geregistreerd). Arch: 291 passed, 3 xfailed (was 9). pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-API-011 Dag 2: 6 xfails gesloten. clear_tenant_cache() caller in delete_tenant (re-export via tenants/dependencies.py). GET /integrations/catalog + GET /integrations/search stubs in tools/integrations_router.py. WebSocket /ws/builder alias (accept+close 1001). POST /{template_id}/deploy + GET /search/ in template_router.py (voor /{template_id} geregistreerd). Arch: 291 passed, 3 xfailed (was 9). pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
