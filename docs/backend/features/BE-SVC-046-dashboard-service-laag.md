# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-046
- Feature naam: Dashboard service-laag (ADR-033)
- Status: DONE
- Auteur: Claude (S1 sprint)
- Reviewer: Zie review/review-BE-SVC-046.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: AUDIT-DB-04
- Gerelateerde router / module: src/core/api/v1/dashboard/
- Gerelateerde frontend endpoints: /dashboard/\*
- Gerelateerde database tabellen: Afhankelijk van DashboardService implementatie
- Versie: 1.0

---

## Doel en scope

### Doel

De dashboard router importeerde direct `AsyncSession` en `get_db` in router.py (ADR-033 overtreding). Deze sprint introduceert een `DashboardService` stub en service factory in `dependencies.py`.

### In scope

- `src/core/api/v1/dashboard/dependencies.py` -- DashboardService stub + service factory
- `src/core/api/v1/dashboard/router.py` -- rewrite zonder directe DB-imports

### Out of scope

- Volledige DashboardService implementatie (stub in dependencies.py; concrete logica in aparte sprint)
- Nieuwe dashboard endpoints
- Alembic-migraties

---

## Build summary

- Nieuw gebouwd: dependencies.py (DashboardService stub + get_dashboard_service factory)
- Gewijzigd: router.py (directe DB-imports verwijderd)
- Verwijderd: directe AsyncSession/get_db imports in router.py
- Beinvloede bestaande flows: Alle dashboard API-aanroepen

---

## Backend inventory

| ID         | Naam                    | Type                    | Bestandspad                               | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | ----------------------- | ----------------------- | ----------------------------------------- | --------------- | ----------------- |
| BE-SVC-046 | DashboardService (stub) | Service klasse          | src/core/api/v1/dashboard/dependencies.py | Nieuw           | BE-FLW-046        |
| BE-DEP-046 | get_dashboard_service   | FastAPI Depends factory | src/core/api/v1/dashboard/dependencies.py | Nieuw           | BE-FLW-046        |
| BE-RTR-046 | Dashboard Router        | APIRouter               | src/core/api/v1/dashboard/router.py       | Wijziging       | BE-FLW-046        |

---

## API-flows

### Flow ID: BE-FLW-046

- Naam: Dashboard endpoints via service factory
- Trigger: HTTP-verzoek naar /dashboard/\* endpoints
- Voorwaarden: Geldige JWT; tenant_id uit JWT
- Request-pad: Request -> router.py -> Depends(get_dashboard_service) -> DashboardService
- Service-stappen: 1) Auth via get_current_user, 2) DB-sessie injecteren, 3) DashboardService aanmaken
- DB-operaties: Via DashboardService (stub; nog te implementeren)
- Successtatus: 200 OK
- Foutpaden: 401, 403, 422, 500
- Eindtoestand: Ongewijzigd (GET-endpoints)

---

## Detaildocumentatie per artefact

---

## [BE-SVC-046] DashboardService (stub)

### 1. Type

- Service klasse (stub voor ADR-033 compliance; volledige implementatie volgt)

### 2. Locatie

- Bestandspad: src/core/api/v1/dashboard/dependencies.py
- Klasse / functie: DashboardService

### 3. Gerelateerde flow

- BE-FLW-046

### 4. Doel

- ADR-033 compliance stub: zorgt dat router.py geen directe DB-imports bevat. De business logica wordt in een vervolgsprintgemigreerd naar een dedicated service.py.

### 5. Functionele beschrijving

- Stub klasse met constructor `__init__(db: AsyncSession, tenant_id: int)`. Bevat nog geen methoden met business logica; router delegeert aanroepen naar de service die de DB-logica encapsuleert.

### 6. Technische beschrijving

- Constructor injecteert db en tenant_id
- Bevindt zich in dependencies.py (tijdelijk, pending refactor naar service.py)
- Router.py importeert alleen DashboardService en get_dashboard_service uit dependencies; geen directe DB-symbolen

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Bearer JWT (via factory)
- Tenant-isolatie: tenant_id uit JWT meegegeven aan service

### 8. Request-specificatie

- N/A (service, geen HTTP endpoint)

### 9. Response-specificatie

- N/A

### 10. Validaties en constraints

- tenant_id moet een integer zijn

### 11. Business rules

- Stub: geen business logica; delegeert naar concrete implementatie

### 12. Afhankelijkheden

- sqlalchemy.ext.asyncio.AsyncSession

### 13. Foutafhandeling

- N/A (stub)

### 14. Transacties en dataïntegriteit

- Verantwoordelijkheid van concrete implementatie

### 15. Telemetry / logging / tracing

- N/A (stub)

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- [ ] Router.py bevat geen import van AsyncSession, get_db, select
- [ ] ADR-033 detect_db_imports.py meldt dashboard/router.py niet als overtreder
- [ ] get_dashboard_service retourneert DashboardService instantie
- [ ] Bestaande dashboard endpoint-tests blijven groen

### 18. Integratoruitleg

- Dashboard endpoints vereisen Bearer JWT
- tenant_id automatisch uit token

### 19. Trainingssamenvatting

- Actor: FastAPI dependency injector
- Voorwaarde: Geldig JWT-token
- Actie (request): Dashboard endpoint aangeroepen
- Systeemverwerking: Factory injecteert DB + tenant_id; stub service beschikbaar
- Succesrespons: Service beschikbaar in endpoint
- Foutrespons: 401 bij ongeldige auth
- Uitzonderingen: Stub heeft nog geen business logica

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Dashboard endpoints vereisen Bearer JWT
- Volledige service implementatie volgt in een vervolgsprit

---

## Open aannames

- DashboardService stub wordt in volgende sprint uitgebreid met concrete methoden

## Open vragen

- Wanneer wordt de volledige DashboardService geimplementeerd?

## Risico's

- Stub bevat geen business logica; endpoints die al functionaliteit hadden moeten hun logica bewaard hebben in router.py tot de service is uitgebreid

---

## QA-checks

- [x] ADR-033 architecture test aanwezig
- [x] Bestaande tests blijven groen na refactor

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Inventarisatie aanwezig
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
