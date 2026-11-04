# BE-RTR-025 — RBAC + Management Domain Migration naar v1/

**Sprint:** SP-API-005 Dag 5
**Datum:** 2026-06-05
**Status:** CLOSED
**ADR:** ADR-033 (API Layer Strangler Fig)

## Samenvatting

Migratie van `rbac_endpoints.py` (434r) en `management_endpoints.py` (341r) naar gestructureerde
drie-laags v1/ domein-pakketten conform ADR-033.

## Bestanden aangemaakt

### v1/rbac/ (RBAC domain)
- `__init__.py` — domain_router met prefix="/api"
- `router.py` — composite router
- `permissions_router.py` — GET /users/{id}/permissions + POST /permissions/check
- `roles_router.py` — POST /roles/create, GET /roles, GET/POST/DELETE /roles/{id}/permissions, GET /roles/{id}/users
- `assignment_router.py` — POST /users/assign-role, revoke-role, bulk varianten
- `dependencies.py` — gedeelde imports

### v1/management/ (Management domain)
- `__init__.py` — domain_router zonder prefix (sub-routers bevatten full prefix "/api/v1")
- `router.py` — composite router
- `agents_router.py` — GET /agents, POST /agents/{id}/pause/resume/restart
- `tasks_router.py` — GET /costs, GET /tasks, POST /tasks/{id}/prioritize/cancel, GET/POST /approvals
- `logs_router.py` — GET /logs, GET /logs/broadcast-queue
- `dependencies.py` — gedeelde imports

## Registry wijzigingen

- `registries/analytics.py:22` — `rbac_router` vervangen door `rbac_domain_router` (v1/rbac/)
- `registries/auth_admin.py:48` — `management_router` vervangen door `management_domain_router` (v1/management/)

## Pre-existing fixes (apart gecommit: 418745b6)

- `management_endpoints.py`: 11 f-string logger calls -> %s formatting
- `rbac_endpoints.py`: unused `Optional` import verwijderd

## Orphan handling

Beide legacy flat files kregen `# orphan:exempt` commentaar op regel 1:
- `rbac_endpoints.py` — shared module-level Pydantic schemas en RBACService imports
- `management_endpoints.py` — shared module-level state (approval_requests, log_entries, log_broadcast_queue)

## Testresultaten

- Nieuwe equivalentietests: `test_rbac_flat_file_migrated_to_v1` + `test_management_flat_file_migrated_to_v1`
- Eindstand: **149 PASS, 0 failures, 0 regressions** op 147 bestaande tests + 2 nieuwe

## Trainingssamenvatting

### Flow 1: RBAC Route Registratie (Domain Migration)

**Actor:** API Layer (FastAPI app startup)
**Voorwaarde:** `registries/analytics.py` wordt uitgevoerd bij `register_all_routers(app)`
**Actie:** `rbac_domain_router` (uit `v1/rbac/__init__.py`) wordt geregistreerd op prefix `/api`
**Systeemverwerking:** Sub-routers `permissions_router`, `roles_router`, `assignment_router` worden via `router.py` composite geladen; elke sub-router heeft prefix `/rbac`
**Succesrespons:** Routes bereikbaar op `/api/rbac/...` — gelijk aan oorspronkelijke `/api/rbac/...` paden uit `rbac_endpoints.py`
**Foutrespons:** ImportError bij ontbrekende sub-router — app startup faalt expliciet
**Uitzonderingen:** Legacy `rbac_endpoints.py` blijft bestaan (orphan:exempt) voor toekomstige verwijdering

### Flow 2: Management Route Registratie (Domain Migration)

**Actor:** API Layer (FastAPI app startup)
**Voorwaarde:** `registries/auth_admin.py` wordt uitgevoerd bij `register_all_routers(app)`
**Actie:** `management_domain_router` (uit `v1/management/__init__.py`) wordt geregistreerd zonder extra prefix
**Systeemverwerking:** Sub-routers `agents_router`, `tasks_router`, `logs_router` worden via `router.py` composite geladen; elke sub-router heeft prefix `/api/v1` intern
**Succesrespons:** Routes bereikbaar op `/api/v1/agents`, `/api/v1/costs`, `/api/v1/tasks`, `/api/v1/approvals`, `/api/v1/logs` — gelijk aan origineel
**Foutrespons:** ImportError bij ontbrekende sub-router — app startup faalt expliciet
**Uitzonderingen:** In-memory state (approval_requests, log_entries) wordt gedeeld via import uit legacy flat file

## Toevoeging 2026-10-04: goedkeuringsroutes verwijderd

Toevoeging 2026-10-04 (OP-264, historische tekst hierboven blijft staan): de routes
`POST /api/v1/approvals/{id}/respond` en `GET /api/v1/approvals` zijn verwijderd, in beide
kopieen (`src/core/api/v1/management/tasks_router.py` en `src/core/api/management_endpoints.py`).
Ook de module-lijst `approval_requests` (met 2 demorijen) en de bijbehorende sleutel in
`shared/app_state.py` bestaan niet meer. Bron: commits d3eb0b52 en a91044fb op tak
`iter/op264-goedkeuringspad`; brief
`docs/agent-briefs/generated/2026-10-04-sprint-dag-op264-een-goedkeuringspad.md`.
Een menselijke goedkeuring loopt alleen nog via `hitl_tickets` (`/api/v1/tools/hitl/*`).
Stand: scenario 5 uit `docs/meetlat.md` is door de acceptant AFGEKEURD; OP-264 is dus niet
gesloten.
