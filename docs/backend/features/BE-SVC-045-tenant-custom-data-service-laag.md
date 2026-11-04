# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-045
- Feature naam: TenantCustomData service-laag (ADR-033)
- Status: DONE
- Auteur: Claude (S1 sprint)
- Reviewer: Zie review/review-BE-SVC-045.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: AUDIT-DB-03
- Gerelateerde router / module: src/core/api/v1/tenant_custom_data/
- Gerelateerde frontend endpoints: /tenant-custom-data/\*
- Gerelateerde database tabellen: tenant_custom_data
- Versie: 1.0

---

## Doel en scope

### Doel

De tenant_custom_data router importeerde direct database-gerelateerde symbolen in router.py. ADR-033 verbiedt dit. De fix verplaatst de service factory naar `dependencies.py`.

### In scope

- `src/core/api/v1/tenant_custom_data/dependencies.py` -- service factory
- `src/core/api/v1/tenant_custom_data/router.py` -- rewrite zonder directe DB-imports

### Out of scope

- Nieuwe TenantCustomData endpoints
- Wijzigingen aan business logica
- Alembic-migraties

---

## Build summary

- Nieuw gebouwd: dependencies.py service factory
- Gewijzigd: router.py (inline \_get_service() verwijderd; factory uit dependencies.py gebruikt)
- Verwijderd: lokale \_get_service() helper in router.py
- Beinvloede bestaande flows: Alle tenant_custom_data API-aanroepen

---

## Backend inventory

| ID         | Naam                           | Type                    | Bestandspad                                        | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | ------------------------------ | ----------------------- | -------------------------------------------------- | --------------- | ----------------- |
| BE-DEP-045 | get_tenant_custom_data_service | FastAPI Depends factory | src/core/api/v1/tenant_custom_data/dependencies.py | Nieuw           | BE-FLW-045        |
| BE-RTR-045 | TenantCustomData Router        | APIRouter               | src/core/api/v1/tenant_custom_data/router.py       | Wijziging       | BE-FLW-045        |

---

## API-flows

### Flow ID: BE-FLW-045

- Naam: TenantCustomData CRUD via service factory
- Trigger: HTTP-verzoek naar /tenant-custom-data/\* endpoints
- Voorwaarden: Geldige JWT; tenant_id uit JWT
- Request-pad: Request -> router.py -> Depends(get_tenant_custom_data_service) -> TenantCustomDataService
- Service-stappen: 1) Auth via get_current_user, 2) DB-sessie injecteren, 3) Service aanmaken
- DB-operaties: Via TenantCustomDataService
- Successtatus: 200/201 OK
- Foutpaden: 401, 403, 404, 422, 500
- Eindtoestand: Afhankelijk van operatie (CRUD)

---

## Detaildocumentatie per artefact

---

## [BE-DEP-045] get_tenant_custom_data_service

### 1. Type

- FastAPI Depends-dependency (service factory)

### 2. Locatie

- Bestandspad: src/core/api/v1/tenant_custom_data/dependencies.py
- Klasse / functie: get_tenant_custom_data_service()

### 3. Gerelateerde flow

- BE-FLW-045

### 4. Doel

- Encapsuleert service-constructie zodat router.py geen directe DB-imports bevat (ADR-033)

### 5. Functionele beschrijving

- Injecteert DB-sessie en current_user; maakt TenantCustomDataService aan. Auth wordt via get_current_user afgedwongen.

### 6. Technische beschrijving

- `Depends(get_db)` voor AsyncSession; `Depends(get_current_user)` voor auth
- Retourneert TenantCustomDataService(db=db, tenant_id=current_user.tenant_id)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Bearer JWT
- Vereiste rol / scope: Authenticated user
- Tenant-isolatie: tenant_id uit JWT; service filtert automatisch
- Feature flag: N/A

### 8. Request-specificatie

- Methode: N/A (Depends-factory)
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Retourneert TenantCustomDataService instantie
- Foutstatussen: 401 bij ongeldige auth

### 10. Validaties en constraints

- Auth verplicht

### 11. Business rules

- Auth afdwingen in factory; nooit in router endpoint zelf

### 12. Afhankelijkheden

- src/core/database.database.get_db
- src/core/auth.api_deps.get_current_user
- TenantCustomDataService

### 13. Foutafhandeling

- 401: get_current_user HTTPException
- 500: DB-sessie onbeschikbaar

### 14. Transacties en dataïntegriteit

- Factory maakt geen transacties

### 15. Telemetry / logging / tracing

- Via OpenTelemetry in DB-laag

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- [ ] Router.py bevat geen import van AsyncSession, get_db, select
- [ ] get_tenant_custom_data_service retourneert service-instantie
- [ ] ADR-033 detect_db_imports.py meldt tenant_custom_data/router.py niet als overtreder
- [ ] Ongeauthenticeerde aanroepen geven 401

### 18. Integratoruitleg

- Gebruik `service = Depends(get_tenant_custom_data_service)` in router endpoints
- Auth is automatisch via de factory

### 19. Trainingssamenvatting

- Actor: FastAPI dependency injector
- Voorwaarde: Geldig JWT-token
- Actie (request): Router endpoint aangeroepen
- Systeemverwerking: Factory injecteert DB + auth; retourneert service
- Succesrespons: Service beschikbaar in endpoint
- Foutrespons: 401 bij ongeldige auth
- Uitzonderingen: N/A

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Alle tenant_custom_data endpoints vereisen Bearer JWT
- tenant_id automatisch uit token; nooit meesturen in request body

---

## Open aannames

- TenantCustomDataService accepteert tenant_id in constructor

## Open vragen

- Geen

## Risico's

- N/A

---

## QA-checks

- [x] ADR-033 architecture test aanwezig
- [x] Auth getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
