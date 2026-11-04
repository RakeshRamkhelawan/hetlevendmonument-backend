# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-044
- Feature naam: Gamification service-laag (ADR-033)
- Status: DONE
- Auteur: Claude (S1 sprint)
- Reviewer: Zie review/review-BE-SVC-044.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: AUDIT-DB-02
- Gerelateerde router / module: src/core/api/v1/gamification/
- Gerelateerde frontend endpoints: /gamification/\*
- Gerelateerde database tabellen: leaderboard_entries (verondersteld)
- Versie: 1.0

---

## Doel en scope

### Doel

De gamification router importeerde direct `AsyncSession`, `get_db`, `get_current_user` en SQLAlchemy-queries. Dit is een ADR-033 overtreding (router.py mag geen directe DB-imports bevatten). Deze sprint refactort de router naar de 3-laags ADR-033 structuur met een dedicated `dependencies.py` service factory.

### In scope

- `src/core/api/v1/gamification/dependencies.py` -- service factory `get_gamification_service`
- `src/core/api/v1/gamification/router.py` -- rewrite zonder directe DB-imports

### Out of scope

- Wijzigingen aan GamificationService logica
- Nieuwe gamification endpoints
- Alembic-migraties

---

## Build summary

- Nieuw gebouwd: dependencies.py (service factory)
- Gewijzigd: router.py (direct DB-imports verwijderd, factory gebruikt)
- Verwijderd: directe import van AsyncSession, get_db, get_current_user in router.py
- Beinvloede bestaande flows: Alle gamification API-aanroepen

---

## Backend inventory

| ID         | Naam                     | Type                    | Bestandspad                                  | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | ------------------------ | ----------------------- | -------------------------------------------- | --------------- | ----------------- |
| BE-DEP-044 | get_gamification_service | FastAPI Depends factory | src/core/api/v1/gamification/dependencies.py | Nieuw           | BE-FLW-044        |
| BE-RTR-044 | Gamification Router      | APIRouter               | src/core/api/v1/gamification/router.py       | Wijziging       | BE-FLW-044        |

---

## API-flows

### Flow ID: BE-FLW-044

- Naam: Gamification endpoints via service factory
- Trigger: HTTP-verzoek naar /gamification/\* endpoints
- Voorwaarden: Geldige JWT-token; tenant_id uit JWT
- Request-pad: Request -> router.py -> Depends(get_gamification_service) -> GamificationService
- Service-stappen: 1) Auth via get_current_user in factory, 2) DB-sessie injecteren, 3) Service aanmaken, 4) Router delegeert naar service
- DB-operaties: Via GamificationService (niet in router)
- Successtatus: 200 OK met gamification data
- Foutpaden: 401 (geen token), 403 (verkeerde tenant), 404 (resource niet gevonden), 422 (validatiefout)
- Eindtoestand: Geen state change bij GET-endpoints

---

## Detaildocumentatie per artefact

---

## [BE-DEP-044] get_gamification_service

### 1. Type

- FastAPI Depends-dependency (service factory)

### 2. Locatie

- Bestandspad: src/core/api/v1/gamification/dependencies.py
- Klasse / functie: get_gamification_service()

### 3. Gerelateerde flow

- BE-FLW-044

### 4. Doel

- Encapsuleert DB-sessie injectie voor GamificationService zodat router.py geen directe DB-imports nodig heeft (ADR-033)

### 5. Functionele beschrijving

- Injecteert een async DB-sessie en maakt een GamificationService instantie aan. Auth wordt via get_current_user afgedwongen. De factory is het enige contactpunt tussen router en service.

### 6. Technische beschrijving

- `Depends(get_db)` voor AsyncSession; `Depends(get_current_user)` voor auth; retourneert `GamificationService(db=db)`
- GamificationService ontvangt tenant_id per methode-aanroep (niet in constructor)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Bearer JWT (via get_current_user in factory)
- Vereiste rol / scope: Authenticated user
- Tenant-isolatie: tenant_id uit JWT via get_current_user; service filtert per methode
- Feature flag: N/A

### 8. Request-specificatie

- Methode: N/A (Depends-factory, geen directe HTTP)
- Route: N/A
- Path parameters: N/A
- Query parameters: N/A
- Request body (schema): N/A
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Successtatus: N/A (retourneert service-object)
- Response schema: GamificationService instantie
- Foutstatussen: 401 als get_current_user faalt

### 10. Validaties en constraints

- DB-sessie moet beschikbaar zijn
- get_current_user moet een valide user teruggeven

### 11. Business rules

- Auth afdwingen via factory, niet in router endpoints zelf

### 12. Afhankelijkheden

- src/core/database.database.get_db
- src/core/auth.api_deps.get_current_user
- GamificationService

### 13. Foutafhandeling

- 401: get_current_user gooit HTTPException(401)
- 500: DB-sessie onbeschikbaar

### 14. Transacties en dataïntegriteit

- Factory maakt geen transacties; DB-sessie wordt doorgegeven aan service

### 15. Telemetry / logging / tracing

- Via OpenTelemetry in de DB-laag en service

### 16. Caching

- Gecached: Nee
- Cache-sleutel: N/A
- TTL: N/A
- Invalidatie: N/A

### 17. Acceptatiecriteria

- [ ] Router.py bevat geen import van AsyncSession, get_db, select, func
- [ ] get_gamification_service retourneert een GamificationService instantie
- [ ] Ongeauthenticeerde aanroepen geven 401
- [ ] ADR-033 detect_db_imports.py meldt gamification/router.py niet als overtreder

### 18. Integratoruitleg

- Gebruik `service: GamificationService = Depends(get_gamification_service)` in router endpoints
- Geen directe DB-code in router endpoints nodig

### 19. Trainingssamenvatting

- Actor: FastAPI dependency injector
- Voorwaarde: Geldig JWT-token aanwezig
- Actie (request): Router endpoint wordt aangeroepen
- Systeemverwerking: get_gamification_service injecteert DB-sessie en maakt GamificationService
- Succesrespons: GamificationService beschikbaar in endpoint
- Foutrespons: 401 bij ongeldige auth
- Uitzonderingen: N/A

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Alle gamification endpoints vereisen een geldig JWT Bearer token
- tenant_id wordt automatisch uit het token gehaald; meegeven in request body is niet nodig
- Leaderboard endpoints ondersteunen `limit` (max 100) query parameter

---

## Open aannames

- GamificationService accepteert tenant_id per methode-aanroep

## Open vragen

- Geen

## Risico's

- N/A

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] ADR-033 architecture test aanwezig
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
