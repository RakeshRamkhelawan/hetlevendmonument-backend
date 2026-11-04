# Backend Feature Specification

## Metadata

- Feature ID: BE-DSM-005
- Feature naam: LearningBudgetService + ADR-034 Category-2 fix admin_learning_endpoints
- Status: APPROVED WITH MINOR GAPS
- Auteur: Claude (SP-DSM-DAG6)
- Reviewer: -
- Datum: 2026-06-14
- Gerelateerde user story / ticket: SP-DSM-DAG6
- Gerelateerde router / module: src/core/api/admin_learning_endpoints.py
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: tenant_llm_budgets
- Versie: 1.0

---

## Doel en scope

### Doel

Verwijder ADR-034 Category-2 schendingen uit `admin_learning_endpoints.py`: directe imports van
`src.core.learning.gdpr_models` en `src.core.learning.twin_models` vanuit de `core_api`-laag.
Fix: nieuwe `LearningBudgetService` in de service-laag abstraheert alle `TenantLLMBudget` ORM-toegang;
een nieuwe API-laag schemasbestand (`admin_learning_schemas.py`) isoleert de GDPR request-schemas.
Daarmee worden de twee CI-blokkerende RED architecture tests groen.

### In scope

- Nieuw bestand `src/core/api/admin_learning_schemas.py` (GDPR request-schemas in core_api-laag)
- Nieuw bestand `src/core/learning/budget_service.py` (LearningBudgetService)
- Refactor `src/core/api/admin_learning_endpoints.py`: verwijder Category-2 imports, delegeer aan services
- Toevoeging rate-limit decorators op GDPR POST + budget PUT endpoints
- Backlog-marker architecture tests voor pre-existing findings in `admin_digital_twin.py`
- Unit tests voor LearningBudgetService (6 tests, geen PostgreSQL vereist)

### Out of scope

- Functionele wijziging van GDPR-verwijder, export, retentie flows
- Alembic-migraties (TenantLLMBudget-tabel bestaat al)
- Frontend-aanpassingen

---

## Build summary

- Nieuw gebouwd: `src/core/api/admin_learning_schemas.py`, `src/core/learning/budget_service.py`,
  `tests/unit/core/learning/test_budget_service.py`,
  `tests/architecture/test_dsm_dag6_preexisting_findings.py`
- Gewijzigd: `src/core/api/admin_learning_endpoints.py`, `src/core/learning/gdpr_models.py`
- Verwijderd: geen bestanden; verwijderde imports: `gdpr_models.*`, `twin_models.TenantLLMBudget`,
  `metrics.set_twin_llm_budget_hard`, `datetime` uit admin_learning_endpoints.py
- Beinvloede bestaande flows: GET + PUT /admin/learning/tenants/{tenant_id}/llm-budget
  (logica ongewijzigd, nu via service-laag)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SCH-026 | GDPRDeleteUserRequest (API-laag) | Schema | src/core/api/admin_learning_schemas.py | Nieuw | - |
| BE-SCH-027 | GDPRExportUserRequest (API-laag) | Schema | src/core/api/admin_learning_schemas.py | Nieuw | - |
| BE-SCH-028 | GDPRRetentionRequest (API-laag) | Schema | src/core/api/admin_learning_schemas.py | Nieuw | - |
| BE-SVC-033 | LearningBudgetService | Service | src/core/learning/budget_service.py | Nieuw | BE-FLW-006, BE-FLW-007 |
| BE-EP-031 | GET /admin/learning/tenants/{tenant_id}/llm-budget | Endpoint | src/core/api/admin_learning_endpoints.py | Wijziging | BE-FLW-006 |
| BE-EP-032 | PUT /admin/learning/tenants/{tenant_id}/llm-budget | Endpoint | src/core/api/admin_learning_endpoints.py | Wijziging | BE-FLW-007 |
| BE-UTL-042 | Backlog-marker architecture tests SP-DSM-DAG6 | Utility | tests/architecture/test_dsm_dag6_preexisting_findings.py | Nieuw | - |

---

## API-flows

### Flow BE-FLW-006 — GET tenant LLM budget

- Naam: Ophalen huidige-maand LLM-budget voor een tenant
- Trigger: GET /admin/learning/tenants/{tenant_id}/llm-budget
- Voorwaarden: JWT Bearer token, rol admin of system_admin; system_admin mag elke tenant opvragen
- Request-pad: router → _enforce_tenant_access → LearningBudgetService.get_budget → DB
- Service-stappen: current_month = datetime.now(timezone.utc).strftime("%Y-%m"); SELECT TenantLLMBudget WHERE tenant_id + month; als None: defaults teruggegeven (soft=10, hard=50, spent=0, remaining_soft=10, remaining_hard=50, created_at=null, updated_at=null) zonder DB-schrijf en zonder Prometheus-aanroep
- DB-operaties: SELECT op tenant_llm_budgets (geen schrijf)
- Successtatus + response: 200 TenantLLMBudgetResponse (tenant_id, month, budget_eur_soft, budget_eur_hard, spent_eur, remaining_soft, remaining_hard, created_at, updated_at)
- Foutpaden: 400 geen tenant context in JWT; 403 non-system_admin vraagt andere tenant; 401 ongeldig token; 500 DB-fout
- Eindtoestand: geen DB-wijziging; Prometheus gauge bijgewerkt als record bestaat

### Flow BE-FLW-007 — PUT tenant LLM budget

- Naam: Aanmaken of bijwerken huidige-maand LLM-budget voor een tenant
- Trigger: PUT /admin/learning/tenants/{tenant_id}/llm-budget
- Voorwaarden: JWT Bearer token, rol admin of system_admin; rate-limit: consent_update_limit (10/min)
- Request-pad: router → _enforce_tenant_access → LearningBudgetService.update_budget → DB + audit log
- Service-stappen: SELECT bestaand record; als None: INSERT TenantLLMBudget; als IntegrityError (race): rollback + re-SELECT + UPDATE; COMMIT; REFRESH; Prometheus gauge update; best_effort audit log
- DB-operaties: SELECT + INSERT of UPDATE op tenant_llm_budgets; INSERT op learning_audit_events (best_effort)
- Successtatus + response: 200 TenantLLMBudgetResponse
- Foutpaden: 400 geen tenant context; 403 toegang geweigerd; 422 budget_eur_hard < budget_eur_soft; 429 rate limit; 500 DB-fout
- Eindtoestand: tenant_llm_budgets bijgewerkt; learning_audit_events regel toegevoegd (best_effort)

---

## Detaildocumentatie per artefact

---

## [BE-SCH-026/027/028] API-laag GDPR request-schemas

### 1. Type

- Pydantic-schema (request)

### 2. Locatie

- Bestandspad: src/core/api/admin_learning_schemas.py
- Klasse: GDPRDeleteUserRequest, GDPRExportUserRequest, GDPRRetentionRequest

### 3. Gerelateerde flow

- Geen directe flow; gebruikt als FastAPI body-parameter in GDPR-endpoints

### 4. Doel

- Isoleer GDPR request-schemas in de core_api-laag zodat admin_learning_endpoints.py geen directe import nodig heeft vanuit src.core.learning (agent_runtime boundary — ADR-034).

### 5. Functionele beschrijving

- Identieke velden als de oorspronkelijke schemas in gdpr_models.py: user_id (str, max 255), reason (optioneel, max 500), max_age_days (int 1-3650).

### 6. Technische beschrijving

- BaseModel met Field-validators; geen from __future__ import annotations (FastAPI valkuil per CLAUDE.md); geen SQLAlchemy-imports.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: via de endpoints die ze gebruiken
- Vereiste rol / scope: admin
- Tenant-isolatie: user_id is een string, niet een tenant-gebonden FK
- Feature flag: geen

### 8. Request-specificatie

- Methode: gebruikt als request body (geen directe route)
- Route: zie GDPR-endpoints in admin_learning_endpoints.py
- Path parameters: n.v.t.
- Query parameters: n.v.t.
- Request body: GDPRDeleteUserRequest { user_id: str, reason: str | None }; GDPRExportUserRequest { user_id: str }; GDPRRetentionRequest { max_age_days: int }
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: n.v.t. (schema, geen endpoint)
- Response schema: n.v.t.
- Foutstatussen: 422 bij Pydantic-validatiefout (te lange string, negatief getal)

### 10. Validaties en constraints

- user_id: min_length=1, max_length=255
- reason: max_length=500
- max_age_days: ge=1, le=3650 (max 10 jaar)

### 11. Business rules

- user_id is een applicatie-gebruikersidentificatie; de service koppelt dit aan de tenant via tenant_id uit JWT.

### 12. Afhankelijkheden

- pydantic.BaseModel, pydantic.Field

### 13. Foutafhandeling

- 422: Pydantic-validatie faalt (FastAPI automatisch)

### 14. Transacties en dataïntegriteit

- n.v.t.

### 15. Telemetry / logging / tracing

- n.v.t. (alleen deserialisatie)

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- GDPRDeleteUserRequest accepteert user_id=str, reason=None (optioneel)
- GDPRDeleteUserRequest weigert user_id="" (min_length=1)
- GDPRRetentionRequest weigert max_age_days=0 en max_age_days=3651
- Pydantic geeft 422 bij te lange user_id (>255 chars)

### 18. Integratoruitleg

- Gebruik user_id als de applicatie-gebruikersidentificatie (niet de database-id)
- reason is optioneel bij verwijdering; bij afwezigheid wordt None opgeslagen
- max_age_days bepaalt de bewaartermijn: data ouder dan dit wordt verwijderd

### 19. Trainingssamenvatting

- Actor: admin-gebruiker
- Voorwaarde: valide JWT met admin-rol
- Actie (request): POST /admin/learning/gdpr/* met JSON body
- Systeemverwerking: Pydantic valideert body; LearningGDPRService voert operatie uit
- Succesrespons: 200 met report
- Foutrespons: 422 bij validatiefout; 429 bij rate limit
- Uitzonderingen: user_id-constraint (letters, cijfers, koppeltekens) geldt voor GDPRDeleteUserRequest en GDPRExportUserRequest; GDPRRetentionRequest heeft geen user_id-veld

---

## [BE-SVC-033] LearningBudgetService

### 1. Type

- Service-klasse

### 2. Locatie

- Bestandspad: src/core/learning/budget_service.py
- Klasse: LearningBudgetService

### 3. Gerelateerde flow

- BE-FLW-006 (GET budget), BE-FLW-007 (PUT budget)

### 4. Doel

- Abstraheert alle TenantLLMBudget ORM-toegang achter een service-interface zodat de core_api-laag (admin_learning_endpoints.py) niet rechtstreeks uit agent_runtime hoeft te importeren (ADR-034).

### 5. Functionele beschrijving

- get_budget(tenant_id): haalt het LLM-budget voor de lopende maand op. Als er geen record is, worden standaardwaarden (soft=10 EUR, hard=50 EUR) teruggegeven zonder DB-schrijf.
- update_budget(tenant_id, soft, hard): maakt een nieuw record aan of werkt het bestaande bij. Handelt een concurrent-INSERT race af via IntegrityError + rollback + re-read. Na elk schrijven wordt de Prometheus-gauge bijgewerkt en een audit-event gelogd (best_effort).

### 6. Technische beschrijving

- get_budget: SELECT TenantLLMBudget WHERE tenant_id + strftime("%Y-%m"); als None: retourneer defaults-dict zonder DB-wijziging, zonder Prometheus-call; als record: set_twin_llm_budget_hard aanroepen, retourneer dict met alle velden inclusief remaining_soft/hard.
- update_budget: SELECT + INSERT (als None) of UPDATE (als record bestaat); try/except IntegrityError: rollback + SELECT met scalar_one() + UPDATE; COMMIT; REFRESH; Prometheus gauge update; async with best_effort: log_learning_audit_event + COMMIT.
- Retourtype: dict[str, Any] (tenant_id, month, budget_eur_soft, budget_eur_hard, spent_eur, remaining_soft, remaining_hard, created_at, updated_at).

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: geen (interne service, aangeroepen vanuit authenticated endpoint)
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: tenant_id altijd meegegeven als parameter; geen cross-tenant toegang mogelijk
- Feature flag: geen

### 8. Request-specificatie

- Methode: Python method calls (geen HTTP)
- Route: n.v.t.
- Path parameters: n.v.t.
- Query parameters: n.v.t.
- Request body: get_budget(tenant_id: int); update_budget(tenant_id: int, budget_eur_soft: float, budget_eur_hard: float)
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: dict[str, Any] met bovengenoemde velden
- Response schema: zie velden in Technische beschrijving
- Foutstatussen: IntegrityError intern afgehandeld; andere DB-fouten propageren als exception

### 10. Validaties en constraints

- budget_eur_hard >= budget_eur_soft gevalideerd in de router-laag (TenantLLMBudgetUpdateRequest)
- tenant_id is altijd een int (gecast door _enforce_tenant_access)

### 11. Business rules

- Prometheus gauge wordt ALLEEN bijgewerkt als er een echt DB-record bestaat (niet bij defaults)
- Audit log mag nooit primaire operatie blokkeren (best_effort)
- Concurrent INSERT race op (tenant_id, month) unique constraint: herstel via re-read, niet door retry van de volledige request

### 12. Afhankelijkheden

- src.core.learning.twin_models.TenantLLMBudget (ORM model)
- src.core.learning.metrics.set_twin_llm_budget_hard (Prometheus gauge)
- src.core.governance.learning_audit.log_learning_audit_event
- src.core.utils.best_effort
- sqlalchemy.exc.IntegrityError

### 13. Foutafhandeling

- 400: n.v.t. (service niveau)
- IntegrityError: rollback + re-read via scalar_one() + update; als scalar_one() NoResultFound gooit (extreme race: rij verdwijnt direct na INSERT): propagateert als 500
- Audit-log failure: silent (best_effort)
- DB-verbindingsfout: propagateert als 500

### 14. Transacties en dataïntegriteit

- INSERT: autocommit na db.commit(); als IntegrityError: rollback + re-read + UPDATE + commit
- REFRESH na elk commit om de meest actuele waarden te hebben
- Audit log in aparte best_effort transactie na de primaire commit

### 15. Telemetry / logging / tracing

- Prometheus gauge: set_twin_llm_budget_hard(tenant_id, budget_eur_hard)
- Audit event: action="budget.updated", resource="tenant_llm_budget:{tenant_id}:{month}"
- Logger: src.core.learning.budget_service (via logging.getLogger)

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- get_budget geeft default-waarden terug als er geen record bestaat; Prometheus NIET aangeroepen
- get_budget geeft DB-waarden terug en roept Prometheus aan als record bestaat
- update_budget maakt een nieuw record aan bij eerste aanroep
- update_budget werkt een bestaand record bij
- update_budget herstelt van IntegrityError door rollback + re-read
- Audit log failure blokkeert update niet
- remaining_soft = max(0, budget_eur_soft - spent_eur); idem remaining_hard

### 18. Integratoruitleg

- Roep LearningBudgetService(db) aan met de AsyncSession uit de Depends-injectie
- get_budget retourneert altijd een dict; nooit een exception als het record ontbreekt
- update_budget is idempotent voor dezelfde maand: herhaald aanroepen overschrijft de waarden
- Concurrent requests voor dezelfde tenant/maand worden veilig afgehandeld

### 19. Trainingssamenvatting

- Actor: interne service-aanroep vanuit admin-endpoint
- Voorwaarde: valide AsyncSession; tenant_id uit JWT
- Actie (request): get_budget(tenant_id) of update_budget(tenant_id, soft, hard)
- Systeemverwerking: DB-SELECT; optioneel INSERT/UPDATE; Prometheus gauge update; audit log
- Succesrespons: dict met budget-velden
- Foutrespons: IntegrityError intern afgehandeld; andere fouten propageren
- Uitzonderingen: geen record = defaults teruggeven, geen 404

---

## [BE-EP-031] GET /admin/learning/tenants/{tenant_id}/llm-budget

### 1. Type

- API-endpoint (GET)

### 2. Locatie

- Bestandspad: src/core/api/admin_learning_endpoints.py
- Functie: get_tenant_llm_budget

### 3. Gerelateerde flow

- BE-FLW-006

### 4. Doel

- Geeft het LLM-budget van de lopende maand terug voor een opgegeven tenant.

### 5. Functionele beschrijving

- Admin-gebruiker vraagt het huidige LLM-budget op voor een tenant. Als er geen expliciete budgetinstelling is, worden de systeemstandaarden teruggegeven. system_admin-gebruikers mogen elk tenant-id opvragen.

### 6. Technische beschrijving

- FastAPI GET-route; Depends(require_admin_role) + Depends(get_db); path-param tenant_id; _enforce_tenant_access controleert non-system_admin toegang; LearningBudgetService.get_budget; TenantLLMBudgetResponse als response_model.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT Bearer token
- Vereiste rol / scope: admin of system_admin
- Tenant-isolatie: non-system_admin mag alleen eigen tenant opvragen; system_admin elke tenant
- Feature flag: geen

### 8. Request-specificatie

- Methode: GET
- Route: /admin/learning/tenants/{tenant_id}/llm-budget
- Path parameters: tenant_id (int)
- Query parameters: geen
- Request body: geen
- Verplichte headers: Authorization: Bearer <JWT>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: TenantLLMBudgetResponse { tenant_id, month, budget_eur_soft, budget_eur_hard, spent_eur, remaining_soft, remaining_hard, created_at, updated_at }
- Foutstatussen: 400 geen tenant context; 401 ongeldig token; 403 verkeerde tenant; 500 DB-fout

### 10. Validaties en constraints

- tenant_id: FastAPI valideert als int via path-param

### 11. Business rules

- Als er geen record is: defaults teruggegeven (soft=10 EUR, hard=50 EUR, spent=0)
- remaining_soft en remaining_hard zijn nooit negatief (max(0, ...))

### 12. Afhankelijkheden

- LearningBudgetService, require_admin_role, get_db

### 13. Foutafhandeling

- 400: _resolve_tenant_id geeft HTTPException als tenant_id ontbreekt in JWT
- 401: require_admin_role gooit 401 bij ontbrekend/ongeldig token
- 403: _enforce_tenant_access gooit 403 bij cross-tenant toegang
- 422: ongeldige path-param (niet-integer)
- 500: onverwachte DB-fout

### 14. Transacties en dataïntegriteit

- Alleen lezen; geen schrijf-operaties

### 15. Telemetry / logging / tracing

- Prometheus gauge bijgewerkt als record bestaat

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- 200 met defaults als geen record bestaat
- 200 met DB-waarden als record bestaat
- 403 als non-system_admin ander tenant-id opvraagt
- 401 zonder token

### 18. Integratoruitleg

- Gebruik tenant_id uit de JWT claim voor normale admins
- Antwoord bevat altijd alle velden; created_at/updated_at zijn null als nog geen record bestaat
- remaining_soft en remaining_hard zijn de nog beschikbare bedragen voor de lopende maand

### 19. Trainingssamenvatting

- Actor: admin-gebruiker
- Voorwaarde: valide JWT met admin-rol; tenant_id in path
- Actie (request): GET /admin/learning/tenants/{tenant_id}/llm-budget
- Systeemverwerking: tenant-isolatiecheck; DB-SELECT; defaults als geen record
- Succesrespons: 200 TenantLLMBudgetResponse
- Foutrespons: 400/401/403 auth-fouten; 500 DB-fout
- Uitzonderingen: geen record geeft defaults, geen 404

---

## [BE-EP-032] PUT /admin/learning/tenants/{tenant_id}/llm-budget

### 1. Type

- API-endpoint (PUT)

### 2. Locatie

- Bestandspad: src/core/api/admin_learning_endpoints.py
- Functie: update_tenant_llm_budget

### 3. Gerelateerde flow

- BE-FLW-007

### 4. Doel

- Maakt het LLM-budget voor de lopende maand aan of werkt het bij voor een opgegeven tenant.

### 5. Functionele beschrijving

- Admin-gebruiker stelt de soft- en hard-cap in voor LLM-kosten van een tenant voor de lopende maand. Als er nog geen record is, wordt het aangemaakt. Concurrent aanroepen voor dezelfde tenant/maand worden veilig afgehandeld.

### 6. Technische beschrijving

- FastAPI PUT-route; @consent_update_limit (10/min); Depends(require_admin_role) + Depends(get_db); path-param tenant_id; body TenantLLMBudgetUpdateRequest; _enforce_tenant_access; LearningBudgetService.update_budget; TenantLLMBudgetResponse als response_model.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT Bearer token
- Vereiste rol / scope: admin of system_admin
- Tenant-isolatie: non-system_admin mag alleen eigen tenant bijwerken
- Feature flag: geen

### 8. Request-specificatie

- Methode: PUT
- Route: /admin/learning/tenants/{tenant_id}/llm-budget
- Path parameters: tenant_id (int)
- Query parameters: geen
- Request body: TenantLLMBudgetUpdateRequest { budget_eur_soft: float (0-100000), budget_eur_hard: float (0-100000, >= budget_eur_soft) }
- Verplichte headers: Authorization: Bearer <JWT>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: TenantLLMBudgetResponse (zelfde als GET)
- Foutstatussen: 400 geen tenant; 401 ongeldig token; 403 cross-tenant; 422 hard < soft; 429 rate limit; 500 DB-fout

### 10. Validaties en constraints

- budget_eur_hard >= budget_eur_soft (field_validator in TenantLLMBudgetUpdateRequest)
- budget_eur_soft en budget_eur_hard: ge=0, le=100000

### 11. Business rules

- PUT is idempotent voor dezelfde maand: herhaald aanroepen overschrijft de waarden
- spent_eur wordt nooit door dit endpoint gewijzigd (alleen door LLM-gebruik)
- Prometheus-gauge wordt bijgewerkt na elke succesvolle schrijf

### 12. Afhankelijkheden

- LearningBudgetService, TenantLLMBudgetUpdateRequest, consent_update_limit, require_admin_role, get_db

### 13. Foutafhandeling

- 400: geen tenant context in JWT
- 401: ongeldig token
- 403: cross-tenant toegang door non-system_admin
- 422: budget_eur_hard < budget_eur_soft; ongeldige veldwaarden
- 429: rate limit overschreden (10/min)
- 500: DB-fout die niet door IntegrityError-handler afgevangen wordt

### 14. Transacties en dataïntegriteit

- INSERT of UPDATE op tenant_llm_budgets; IntegrityError-race afgehandeld in service
- Audit log in aparte best_effort transactie

### 15. Telemetry / logging / tracing

- Prometheus gauge: set_twin_llm_budget_hard na succesvolle schrijf
- Audit event: action="budget.updated"

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- 200 bij aanmaken (geen bestaand record)
- 200 bij bijwerken (bestaand record)
- 422 als budget_eur_hard < budget_eur_soft
- 429 bij meer dan 10 verzoeken per minuut
- 403 bij cross-tenant toegang

### 18. Integratoruitleg

- Stuur budget_eur_soft en budget_eur_hard mee in EUR; beide verplicht
- hard cap moet altijd >= soft cap zijn; anders 422
- Aanmaken en bijwerken gebruiken hetzelfde endpoint; maak geen onderscheid

### 19. Trainingssamenvatting

- Actor: admin-gebruiker
- Voorwaarde: valide JWT met admin-rol; tenant_id in path; hard >= soft
- Actie (request): PUT /admin/learning/tenants/{tenant_id}/llm-budget met budgetvelden
- Systeemverwerking: isolatiecheck; LearningBudgetService create-or-update; Prometheus; audit log
- Succesrespons: 200 TenantLLMBudgetResponse
- Foutrespons: 422 validatie; 429 rate limit; 500 DB-fout
- Uitzonderingen: concurrent inserts worden afgevangen via IntegrityError + re-read

---

## [BE-UTL-042] Backlog-marker architecture tests SP-DSM-DAG6

### 1. Type

- Architecture test (backlog marker)

### 2. Locatie

- Bestandspad: tests/architecture/test_dsm_dag6_preexisting_findings.py
- Functie: test_admin_digital_twin_no_text_fstring, test_admin_digital_twin_stats_has_rate_limit

### 3. Gerelateerde flow

- n.v.t.

### 4. Doel

- Bewaken dat pre-existing bevindingen uit de Laag A review niet vergeten worden (verplicht per quality-gates.md: elke FA-bevinding die niet direct gefixed wordt, vereist een falende architecture test).

### 5. Functionele beschrijving

- test_admin_digital_twin_no_text_fstring: detecteert het text(f"...") patroon in admin_digital_twin.py (KRITIEK — int()-cast maakt injectie onmogelijk maar het patroon moet weg).
- test_admin_digital_twin_stats_has_rate_limit: detecteert het ontbreken van een rate-limit decorator op GET /stats (MEDIUM).

### 6. Technische beschrijving

- Beide tests lezen admin_digital_twin.py via pathlib en doorzoeken de broncode met string-matching.
- Staan intentioneel RED totdat de onderliggende bevindingen gefixed zijn in een volgend sprint-item.

### 7. Acceptatiecriteria

- Beide tests zijn RED zolang de bevindingen niet gefixed zijn (CI faalt = backlog zichtbaar)
- Beide tests worden GREEN zodra de fix geland is

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- LLM-budget per tenant per maand instellen: PUT /admin/learning/tenants/{tenant_id}/llm-budget
- Huidig budget opvragen: GET /admin/learning/tenants/{tenant_id}/llm-budget
- Wanneer geen budget is ingesteld: standaardwaarden (soft 10 EUR, hard 50 EUR) worden teruggegeven
- Rate limit PUT: 10 verzoeken per minuut per tenant
- JWT moet admin- of system_admin-rol bevatten; non-system_admin ziet alleen eigen tenant

---

## Open aannames

- spent_eur wordt bijgehouden door een ander onderdeel van het systeem (LLM-usage tracking); dit endpoint werkt alleen budgetten bij
- De Prometheus-gauge-naam voor set_twin_llm_budget_hard is reeds geregistreerd in src/core/learning/metrics.py

## Open vragen

- Moet remaining_soft/hard ook negatief kunnen zijn (overschrijding melden)? Huidige implementatie: max(0, ...)
- Moeten budget-wijzigingen een notification triggeren (e.g. Dramatiq event)?

## Risico's

- Geen lock op TenantLLMBudget tijdens update: gelijktijdige updates overschrijven elkaar (last-write-wins); voor admin-use-case acceptabel
- best_effort audit log: als de audit-DB niet beschikbaar is, wordt de budget-update niet teruggedraaid; dit is een bewuste keuze per ADR-026

---

## QA-checks

- [x] Endpoint functioneel getest (happy path via unit tests)
- [x] Alle foutstatus-codes gedocumenteerd
- [x] Auth en permissies beschreven
- [x] Tenant-isolatie beschreven (_enforce_tenant_access)
- [x] Validaties beschreven (hard >= soft)
- [x] Edge cases beschreven (geen record = defaults, IntegrityError race)
- [x] Dataïntegriteit beschreven (IntegrityError-handler)
- [ ] Performance / load getest (niet van toepassing voor admin-endpoint)
- [ ] Caching getest (geen caching)
- [x] Logging en tracing beschreven (Prometheus + audit log)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en schemas zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] Review door reviewer-prompt: APPROVED WITH MINOR GAPS (review-BE-DSM-005.md, 2026-06-14)
