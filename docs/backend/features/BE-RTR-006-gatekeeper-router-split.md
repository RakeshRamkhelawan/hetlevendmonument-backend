# Backend Feature Specification

## Metadata

- Feature ID: BE-RTR-006
- Feature naam: Gatekeeper Router Pragmatic Split
- Status: APPROVED
- Auteur: AI Agent (SP-API-002 Dag 1)
- Reviewer: AI Agent (review-BE-RTR-006)
- Datum: 2026-06-02
- Gerelateerde user story / ticket: SP-API-002 Dag 1 — API Layer Grade A+ Refactoring
- Gerelateerde router / module: src/core/api/v1/gatekeeper/
- Gerelateerde frontend endpoints: N.v.t.
- Gerelateerde database tabellen: gatekeeper_decisions, hitl_requests
- Versie: 1.0

---

## Doel en scope

### Doel

Splits de gatekeeper router (360 regels) in twee sub-routers van maximaal 200 regels elk, conform ADR-033. De sprint brief veronderstelde policy-CRUD/allowlist/blocklist endpoints, maar de werkelijke router bevat alleen decision-listing, HITL approval/rejection, en stats. De split is daarom pragmatisch:
- decisions_router: /decisions, /decisions/{task_id}, /decisions/{task_id}/chain, /stats
- hitl_router: /hitl/approve, /hitl/reject

### In scope

- Aanmaken `gatekeeper_decisions_router.py` (<=200r)
- Aanmaken `gatekeeper_hitl_router.py` (<=200r)
- Herschrijven `router.py` als composite router
- Behavioural equivalence tests

### Out of scope

- Wijzigen endpoint-gedrag, URL's, response schema's
- Wijzigen database modellen
- Nieuwe endpoints toevoegen

---

## Build summary

- Nieuw gebouwd:
  - `src/core/api/v1/gatekeeper/gatekeeper_decisions_router.py`
  - `src/core/api/v1/gatekeeper/gatekeeper_hitl_router.py`
  - `tests/unit/api/test_gatekeeper_router_equivalence.py`
- Gewijzigd:
  - `src/core/api/v1/gatekeeper/router.py` — composite router
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: geen (behavioural equivalence bewaard)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-RTR-006 | Gatekeeper Decisions Router | Router | `src/core/api/v1/gatekeeper/gatekeeper_decisions_router.py` | Nieuw | Gatekeeper decisions |
| BE-RTR-006a | Gatekeeper HITL Router | Router | `src/core/api/v1/gatekeeper/gatekeeper_hitl_router.py` | Nieuw | Gatekeeper HITL |
| BE-RTR-006b | Gatekeeper Composite Router | Router | `src/core/api/v1/gatekeeper/router.py` | Wijziging | Gatekeeper composite |
| BE-UTL-006c | Gatekeeper Equivalence Test | Test | `tests/unit/api/test_gatekeeper_router_equivalence.py` | Nieuw | QA |

---

## API-flows

### Flow ID: BE-FLW-010

- Naam: Gatekeeper Decision Listing
- Trigger: GET /api/v1/gatekeeper/decisions
- Voorwaarden: JWT auth, tenant_id uit JWT claim
- Request-pad: client → TenantMiddleware → auth → get_tenant_id → list_decisions
- Service-stappen: extract tenant → build query → count → paginate → serialize
- DB-operaties: SELECT + COUNT op gatekeeper_decisions met tenant_id filter
- Successtatus + response: 200 OK + DecisionListResponse
- Foutpaden: 401 (geen tenant), 404 (geen decisions voor task)
- Eindtoestand: ongewijzigd (read-only)

### Flow ID: BE-FLW-011

- Naam: HITL Approval
- Trigger: POST /api/v1/gatekeeper/hitl/approve
- Voorwaarden: JWT auth, tenant_id uit JWT claim, HITL ticket in pending status
- Request-pad: client → auth → get_tenant_id → approve_hitl
- Service-stappen: zoek ticket → valideer tenant → check status → update naar approved
- DB-operaties: UPDATE hitl_requests SET status='approved'
- Successtatus + response: 200 OK + HITLResponse
- Foutpaden: 400 (niet pending), 401 (geen tenant), 403 (verkeerde tenant), 404 (ticket niet gevonden)
- Eindtoestand: HITL ticket status = approved

---

## Detaildocumentatie per artefact

---

## [BE-RTR-006] Gatekeeper Decisions Router

### 1. Type

Router (APIRouter)

### 2. Locatie

- Bestandspad: `src/core/api/v1/gatekeeper/gatekeeper_decisions_router.py`
- Klasse / functie: `router = APIRouter(prefix="/api/v1/gatekeeper", tags=["Gatekeeper"])`

### 3. Gerelateerde flow

BE-FLW-010 (Decision Listing), BE-FLW-012 (Task Chain Verification), BE-FLW-013 (Gatekeeper Stats)

### 4. Doel

Bevat alle decision-gerelateerde endpoints: listing, retrieval per task, hash chain verification, en statistieken.

### 5. Functionele beschrijving

Biedt inzicht in gatekeeper beslissingen per tenant, inclusief hash chain integriteit en statistische samenvattingen.

### 6. Technische beschrijving

- FastAPI APIRouter met prefix `/api/v1/gatekeeper`
- Gebruikt `GatekeeperRepository` voor database-operaties
- `_db_record_to_response` helper converteert ORM records naar Pydantic responses
- Hash chain verification vergelijkt `previous_hash` met vorige `decision_hash`

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT
- Vereiste rol / scope: authenticated user
- Tenant-isolatie: `tenant_id` uit JWT via `get_tenant_id()`

### 8. Request-specificatie

- Methode: GET
- Route: `/api/v1/gatekeeper/decisions`
- Path parameters: n.v.t.
- Query parameters: `limit` (default 50, max 1000), `offset` (default 0), `task_id` (optional)
- Request body: n.v.t.
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `DecisionListResponse` — {data: DecisionResponse[], total, limit, offset}
- Foutstatussen: 401 Unauthorized, 403 Forbidden, 404 Not Found

### 10. Validaties en constraints

- `limit` tussen 1 en 1000
- `offset` >= 0

### 11. Business rules

- Alleen decisions van de huidige tenant worden getoond
- Hash chain van lege lijst is geldig (`chain_valid=True`)
- Stats bevatten counts per decision type en HITL status

### 12. Afhankelijkheden

- `src.core.als.enterprise.gatekeeper_repository.GatekeeperRepository`
- `src.core.governance.models.GatekeeperDecision`
- `src.core.governance.models.HITLRequestModel`
- `src.core.api.v1.gatekeeper.schemas`

### 13. Foutafhandeling

- 400: ongeldige query parameters
- 401: ontbrekende tenant context
- 403: niet geautoriseerd voor deze HITL request
- 404: geen decisions gevonden voor task
- 500: database fout

### 14. Transacties en data-integriteit

Read-only endpoints; geen expliciete transacties.

### 15. Telemetry / logging / tracing

Structured logging via `logger.info` met tenant_id, limit, offset, count.

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- [ ] Router bestand is <= 200 regels
- [ ] Alle originele routes zijn behouden
- [ ] Composite router dekt exact dezelfde routes als origineel
- [ ] Equivalence test is groen
- [ ] Hash chain verification werkt correct voor lege en niet-lege lijsten

### 18. Integratoruitleg

- Gebruik `GET /api/v1/gatekeeper/decisions` om beslissingen op te halen
- Filter op `task_id` om beslissingen voor een specifieke taak te zien
- Gebruik `GET /api/v1/gatekeeper/decisions/{task_id}/chain` om hash-integriteit te verifiëren
- Gebruik `GET /api/v1/gatekeeper/stats` voor statistisch overzicht

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: JWT token met geldige tenant
- Actie (request): GET /api/v1/gatekeeper/decisions?task_id=abc123
- Systeemverwerking: Valideer auth → extract tenant_id → query decisions → paginate → serialize
- Succesrespons: 200 OK + lijst van decisions
- Foutrespons: 401 Unauthorized, 404 Not Found
- Uitzonderingen: Geen

---

## [BE-RTR-006a] Gatekeeper HITL Router

### 1. Type

Router (APIRouter)

### 2. Locatie

- Bestandspad: `src/core/api/v1/gatekeeper/gatekeeper_hitl_router.py`
- Klasse / functie: `router = APIRouter(prefix="/api/v1/gatekeeper", tags=["Gatekeeper"])`

### 3. Gerelateerde flow

BE-FLW-011 (HITL Approval), BE-FLW-014 (HITL Rejection)

### 4. Doel

Bevat HITL actie-endpoints: approve en reject.

### 5. Functionele beschrijving

Laat geautoriseerde gebruikers toe om pending HITL requests goed- of af te keuren.

### 6. Technische beschrijving

- FastAPI APIRouter met prefix `/api/v1/gatekeeper`
- Gebruikt `GatekeeperRepository` voor database-operaties
- Valideert tenant ownership en pending status voor wijziging

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT
- Vereiste rol / scope: authenticated user
- Tenant-isolatie: `tenant_id` uit JWT, ticket moet tot zelfde tenant behoren

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/gatekeeper/hitl/approve`
- Path parameters: n.v.t.
- Query parameters: n.v.t.
- Request body: `HITLApprovalRequest` — {ticket_ref: str, approved_by: str}
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `HITLResponse` — {status: "approved", ticket_ref, message}
- Foutstatussen: 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found

### 10. Validaties en constraints

- `ticket_ref` moet bestaan
- Ticket moet in status `pending` zijn
- Ticket moet tot zelfde tenant behoren als gebruiker

### 11. Business rules

- Een ticket kan maar één keer worden goed- of afgekeurd
- Na approval/rejection is het ticket immutable
- Approval/rejection wordt gelogd met gebruiker en timestamp

### 12. Afhankelijkheden

- `src.core.als.enterprise.gatekeeper_repository.GatekeeperRepository`
- `src.core.api.v1.gatekeeper.schemas.HITLApprovalRequest`
- `src.core.api.v1.gatekeeper.schemas.HITLRejectionRequest`
- `src.core.api.v1.gatekeeper.schemas.HITLResponse`

### 13. Foutafhandeling

- 400: ticket is niet pending, of reeds verwerkt
- 401: ontbrekende tenant context
- 403: ticket behoort tot andere tenant
- 404: ticket niet gevonden
- 500: database fout bij update

### 14. Transacties en data-integriteit

Write-operatie; `update_hitl_status` in repository handelt transactie af.

### 15. Telemetry / logging / tracing

Structured logging via `logger.info` met tenant_id, ticket_ref, approved_by/rejected_by.

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- [ ] Router bestand is <= 200 regels
- [ ] Alle originele routes zijn behouden
- [ ] Equivalence test is groen
- [ ] Tenant-isolatie behouden (ticket van andere tenant = 403)
- [ ] Status-validatie behouden (niet-pending = 400)

### 18. Integratoruitleg

- Gebruik `POST /api/v1/gatekeeper/hitl/approve` om een pending HITL ticket goed te keuren
- Gebruik `POST /api/v1/gatekeeper/hitl/reject` om een pending HITL ticket af te keuren
- Body: `{ticket_ref: "TKT-123", approved_by: "user@example.com"}`
- Een ticket kan maar één keer worden verwerkt

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: JWT token met geldige tenant; HITL ticket bestaat en is pending
- Actie (request): POST /api/v1/gatekeeper/hitl/approve met {ticket_ref, approved_by}
- Systeemverwerking: Valideer auth → zoek ticket → check tenant → check status → update naar approved
- Succesrespons: 200 OK + {status: "approved", ticket_ref, message}
- Foutrespons: 400 (niet pending), 403 (verkeerde tenant), 404 (ticket niet gevonden)
- Uitzonderingen: Ticket kan maar één keer worden verwerkt

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

De gatekeeper API is onderverdeeld in twee logische groepen:
1. **Decisions** (read-only): decisions, chain verification, stats — gebruik deze voor audit en monitoring
2. **HITL** (write): approve, reject — gebruik deze voor human-in-the-loop besluitvorming

Alle endpoints vereisen JWT authenticatie. Tenant-isolatie is automatisch op basis van het JWT token.

---

## Open aannames

- De sprint brief beschreef policy-CRUD/allowlist/blocklist endpoints, maar deze bestaan niet in de huidige gatekeeper router. De split is daar pragmatisch aangepast.

## Open vragen

- Geen

## Risico's

- Minimaal: enkel structuurwijziging, geen gedragswijziging

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — equivalence tests
- [x] Auth en permissies getest — dependency structuur behouden
- [x] Tenant-isolatie getest — zelfde filtering als origineel
- [x] Equivalence test groen

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
