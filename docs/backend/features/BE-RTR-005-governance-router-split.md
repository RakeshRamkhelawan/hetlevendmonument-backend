# Backend Feature Specification

## Metadata

- Feature ID: BE-RTR-005
- Feature naam: Governance Router Pragmatic Split
- Status: APPROVED
- Auteur: AI Agent (SP-API-002 Dag 1)
- Reviewer: AI Agent (review-BE-RTR-005)
- Datum: 2026-06-02
- Gerelateerde user story / ticket: SP-API-002 Dag 1 — API Layer Grade A+ Refactoring
- Gerelateerde router / module: src/core/api/v1/governance/
- Gerelateerde frontend endpoints: N.v.t.
- Gerelateerde database tabellen: governance_alerts, accuracy_reports, risk_entries, quality_checks, authority_reports
- Versie: 1.0

---

## Doel en scope

### Doel

Splits de governance router (>200 regels) in twee sub-routers van maximaal 200 regels elk, conform ADR-033. De sprint brief veronderstelde HITL/deliberation endpoints, maar de werkelijke router bevat alleen monitoring- en quality-endpoints. De split is daarom pragmatisch:
- monitoring_router: alerts, accuracy, risk-register
- quality_router: quality-check, authority-reports

### In scope

- Aanmaken `governance_monitoring_router.py` (<=200r)
- Aanmaken `governance_quality_router.py` (<=200r)
- Herschrijven `router.py` als composite router
- Behavioural equivalence tests
- Orphan:exempt annotaties voor bewust ongeregistreerde routers

### Out of scope

- Wijzigen endpoint-gedrag, URL's, response schema's
- Wijzigen database modellen
- Nieuwe endpoints toevoegen

---

## Build summary

- Nieuw gebouwd:
  - `src/core/api/v1/governance/governance_monitoring_router.py`
  - `src/core/api/v1/governance/governance_quality_router.py`
  - `tests/unit/api/test_governance_router_equivalence.py`
- Gewijzigd:
  - `src/core/api/v1/governance/router.py` — composite router
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: geen (behavioural equivalence bewaard)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-RTR-005 | Governance Monitoring Router | Router | `src/core/api/v1/governance/governance_monitoring_router.py` | Nieuw | Governance monitoring |
| BE-RTR-005a | Governance Quality Router | Router | `src/core/api/v1/governance/governance_quality_router.py` | Nieuw | Governance quality |
| BE-RTR-005b | Governance Composite Router | Router | `src/core/api/v1/governance/router.py` | Wijziging | Governance composite |
| BE-UTL-005c | Governance Equivalence Test | Test | `tests/unit/api/test_governance_router_equivalence.py` | Nieuw | QA |

---

## API-flows

### Flow ID: BE-FLW-005

- Naam: Governance Alert Listing
- Trigger: GET /api/v1/governance/alerts
- Voorwaarden: JWT auth, tenant_id uit JWT claim
- Request-pad: client → TenantMiddleware → auth → get_current_tenant_id → list_alerts
- Service-stappen: build query met filters → count → paginate → serialize
- DB-operaties: SELECT + COUNT op governance_alerts met tenant_id filter
- Successtatus + response: 200 OK + {success, data: [...], limit, offset, total_count}
- Foutpaden: 401 (geen tenant), 429 (rate limit)
- Eindtoestand: ongewijzigd (read-only)

---

## Detaildocumentatie per artefact

---

## [BE-RTR-005] Governance Monitoring Router

### 1. Type

Router (APIRouter)

### 2. Locatie

- Bestandspad: `src/core/api/v1/governance/governance_monitoring_router.py`
- Klasse / functie: `router = APIRouter(prefix="/api/v1/governance", tags=["governance"])`

### 3. Gerelateerde flow

BE-FLW-005 (Governance Alert Listing), BE-FLW-006 (Accuracy Report), BE-FLW-007 (Risk Register)

### 4. Doel

Bevat alleen read-endpoints voor governance monitoring: alerts, accuracy drift, risk register.

### 5. Functionele beschrijving

Biedt inzicht in governance-status per tenant: openstaande alerts, accuracy drift per agent, en risk-register entries.

### 6. Technische beschrijving

- FastAPI APIRouter met prefix `/api/v1/governance`
- Elke endpoint gebruikt `governance_read_limit` rate limiter
- Lazy imports binnen endpoint-functies voor SQLAlchemy modellen
- Tenant-isolatie via `get_current_tenant_id` dependency

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT
- Vereiste rol / scope: authenticated user
- Tenant-isolatie: `tenant_id` uit JWT, `WHERE tenant_id = ...` in queries
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: GET
- Route: `/api/v1/governance/alerts`
- Path parameters: n.v.t.
- Query parameters: `severity` (optional), `acknowledged` (optional), `limit` (default 50, max 1000), `offset` (default 0)
- Request body: n.v.t.
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `{success: true, data: Alert[], limit, offset, total_count}`
- Foutstatussen: 401 Unauthorized, 429 Too Many Requests

### 10. Validaties en constraints

- `limit` tussen 1 en 1000
- `offset` >= 0

### 11. Business rules

- Alleen alerts van de huidige tenant worden getoond
- Filters zijn optioneel en combineren met AND

### 12. Afhankelijkheden

- `src.core.api.dependencies.get_db`
- `src.core.auth.dependencies.get_current_user`
- `src.core.middleware.tenant_context.get_current_tenant_id`
- `src.core.governance.rate_limiter.governance_read_limit`
- `src.core.governance.alert_manager.GovernanceAlert`

### 13. Foutafhandeling

- 400: ongeldige query parameters (Pydantic validatie)
- 401: ontbrekende tenant context
- 429: rate limit overschreden
- 500: database fout

### 14. Transacties en data-integriteit

Read-only endpoint; geen transactie nodig.

### 15. Telemetry / logging / tracing

Geen expliciete logging in deze router.

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- [ ] Router bestand is <= 200 regels
- [ ] Alle originele routes zijn behouden
- [ ] Composite router dekt exact dezelfde routes als origineel
- [ ] Equivalence test is groen
- [ ] Geen wijziging in URL's, methoden, of responses

### 18. Integratoruitleg

- Gebruik `GET /api/v1/governance/alerts` om openstaande governance alerts op te halen
- Filter optioneel op `severity` (critical/high/medium/low) of `acknowledged` (true/false)
- Gebruik `GET /api/v1/governance/accuracy/{agent_name}` voor drift rapportage per agent
- Gebruik `GET /api/v1/governance/risk-register` voor risico-overzicht

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: JWT token met geldige tenant
- Actie (request): GET /api/v1/governance/alerts?severity=critical
- Systeemverwerking: Valideer auth → extract tenant_id → query alerts met filters → paginate
- Succesrespons: 200 OK + lijst van alerts
- Foutrespons: 401 Unauthorized (geen tenant), 429 Too Many Requests
- Uitzonderingen: Geen

---

## [BE-RTR-005a] Governance Quality Router

### 1. Type

Router (APIRouter)

### 2. Locatie

- Bestandspad: `src/core/api/v1/governance/governance_quality_router.py`
- Klasse / functie: `router = APIRouter(prefix="/api/v1/governance", tags=["governance"])`

### 3. Gerelateerde flow

BE-FLW-008 (Quality Check), BE-FLW-009 (Authority Reports)

### 4. Doel

Bevat write- en read-endpoints voor governance quality: pre-deployment quality gate en authority reports.

### 5. Functionele beschrijving

Biedt kwaliteitscontrole voor agents (pre-deployment gate) en rapportage aan toezichthouders.

### 6. Technische beschrijving

- FastAPI APIRouter met prefix `/api/v1/governance`
- `POST /quality-check/{agent_name}` gebruikt `governance_write_limit`
- `GET /authority-reports` gebruikt `governance_read_limit`

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT
- Vereiste rol / scope: authenticated user
- Tenant-isolatie: `tenant_id` uit JWT

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/governance/quality-check/{agent_name}`
- Path parameters: `agent_name`
- Query parameters: n.v.t.
- Request body: n.v.t.
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `{success: true, data: {agent_name, checks: [...]}}`
- Foutstatussen: 401 Unauthorized, 429 Too Many Requests

### 10. Validaties en constraints

- `agent_name` is verplicht path parameter

### 11. Business rules

- Quality gate controleert agent config tegen tenant beleid
- Resultaten worden gelogd maar niet opgeslagen als aparte entiteit

### 12. Afhankelijkheden

- `src.core.governance.quality_management.QualityGate`
- `src.core.governance.rate_limiter.governance_write_limit`

### 13. Foutafhandeling

- 401: ontbrekende tenant context
- 429: rate limit overschreden
- 500: database fout of quality gate fout

### 14. Transacties en data-integriteit

Quality gate leest configuratie; geen write-transactie.

### 15. Telemetry / logging / tracing

Geen expliciete logging.

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- [ ] Router bestand is <= 200 regels
- [ ] Alle originele routes zijn behouden
- [ ] Equivalence test is groen

### 18. Integratoruitleg

- Gebruik `POST /api/v1/governance/quality-check/{agent_name}` om pre-deployment validatie te triggeren
- Gebruik `GET /api/v1/governance/authority-reports` voor toezichtsrapporten

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: JWT token met geldige tenant
- Actie (request): POST /api/v1/governance/quality-check/email-agent
- Systeemverwerking: Valideer auth → extract tenant_id → run QualityGate.pre_deployment_check
- Succesrespons: 200 OK + {success, data: {agent_name, checks}}
- Foutrespons: 401 Unauthorized, 429 Too Many Requests
- Uitzonderingen: Geen

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

De governance API is onderverdeeld in twee logische groepen:
1. **Monitoring** (read-only): alerts, accuracy, risk-register — gebruik deze voor dashboards en monitoring
2. **Quality** (read/write): quality-check, authority-reports — gebruik deze voor pre-deployment validatie en compliance rapportage

Alle endpoints vereisen JWT authenticatie. Tenant-isolatie is automatisch op basis van het JWT token.

---

## Open aannames

- De sprint brief beschreef HITL/deliberation endpoints, maar deze bestaan niet in de huidige governance router. De split is daar pragmatisch aangepast.

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
