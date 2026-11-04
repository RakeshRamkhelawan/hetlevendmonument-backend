# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-025
- Feature naam: AuditLoggingMiddleware registratie + FA-001 tenant fallback (GOV-001)
- Status: DONE
- Auteur: Uitvoerende agent SP-SEC-001 Dag 1
- Reviewer: Zie docs/backend/review/review-BE-SEC-025.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: SP-SEC-001 GOV-001 + FA-001 (multidisciplinaire audit 2026-06-30)
- Gerelateerde router / module: middleware_config, audit_middleware
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: request_audit_logs
- Versie: 1.0

---

## Doel en scope

### Doel

GOV-001: AuditLoggingMiddleware was al aanwezig in middleware_config.py (pre-existing fix).
FA-001 (BLOCKER door code-reviewer): `_extract_user_info()` hardcodeerde `"0"` als tenant_id
wanneer `request.state.user` ontbreekt (publieke endpoints). Fix: ContextVar fallback via
`get_tenant_id()` -- middleware logt correct de tenant ook voor niet-geauthenticeerde requests.

### In scope

- `src/core/middleware/audit_middleware.py`: `_extract_user_info()` methode -- FA-001 fix
- 2 unit tests (regression guards GOV-001) + 2 architecture tests
- Verificatie dat `AuditLoggingMiddleware` aanwezig is in middleware_config.py

### Out of scope

- Wijzigingen aan middleware_config.py (al correct)
- DB write-logica in `_write_to_db()`
- Nieuwe audit-velden

---

## Build summary

- Nieuw gebouwd: 2 unit tests, 2 architecture tests
- Gewijzigd: `src/core/middleware/audit_middleware.py` (_extract_user_info methode)
- Verwijderd: --
- Beinvloede bestaande flows: alle API-requests -- tenant_id in audit log nu correct ook voor publieke endpoints

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-025-GOV-001 | AuditLoggingMiddleware registratie verificatie | BE-MID | src/core/middleware/middleware_config.py | Verificatie (pre-existing) | Alle API-requests |
| BE-SEC-025-FA-001 | _extract_user_info ContextVar tenant fallback | BE-MID | src/core/middleware/audit_middleware.py | Wijziging | Alle API-requests |

---

## API-flows

### Flow BE-FLW-SEC-025

- Naam: Audit log tenant-resolutie
- Trigger: elk HTTP-verzoek via ASGI-stack
- Voorwaarden: AuditLoggingMiddleware actief na TenantMiddleware in LIFO-stack
- Request-pad: request binnenkomt -> TenantMiddleware zet ContextVar -> AuditLoggingMiddleware logt
- Service-stappen: 1) check `request.state.user`, 2) als None: `get_tenant_id()` ContextVar, 3) fallback `"0"`
- DB-operaties: optional `request_audit_logs` write (best-effort)
- Successtatus: audit log bevat correcte tenant_id
- Foutpaden: ContextVar ook None -> `"0"` (system/unauthenticated namespace)
- Eindtoestand: audit log correct getagged

---

## Detaildocumentatie per artefact

---

## [BE-SEC-025-FA-001] _extract_user_info() -- audit_middleware.py

### 1. Type

- Middleware methode

### 2. Locatie

- Bestandspad: src/core/middleware/audit_middleware.py
- Klasse / functie: `AuditLoggingMiddleware._extract_user_info()`

### 4. Doel

Correcte tenant_id bepalen voor audit log entries, ook voor publieke endpoints zonder
geauthenticeerde gebruiker.

### 5. Functionele beschrijving

- Tenant-resolutie volgorde (FA-001):
  1. `request.state.user.tenant_id` (geauthenticeerde requests via auth middleware)
  2. `get_tenant_id()` ContextVar (publieke endpoints -- gezet door TenantMiddleware)
  3. `"0"` (systeem/unauthenticated zonder tenant context)

### 6. Technische beschrijving

```python
else:
    ctx_tenant_id = get_tenant_id()
    if ctx_tenant_id is not None:
        tenant_id = str(ctx_tenant_id)
```

TenantMiddleware wordt als LAATSTE toegevoegd via `add_middleware()` en is daardoor de
BUITENSTE middleware in de LIFO-stack -- loopt altijd voor AuditLoggingMiddleware.

### 17. Acceptatiecriteria

- Bij geauthenticeerde request: tenant_id uit `request.state.user.tenant_id`
- Bij publieke request met TenantMiddleware context: tenant_id uit `get_tenant_id()`
- Bij volledig anoniem request: `"0"`
- Geen KeyError of AttributeError bij ontbrekende request.state attributen

### 19. Trainingssamenvatting

- Actor: AuditLoggingMiddleware
- Voorwaarde: HTTP-request verwerkt door ASGI-stack
- Actie: `_extract_user_info(request)` aangeroepen na afhandeling request
- Systeemverwerking: user_id uit request.state.user; tenant_id via 3-staps resolutie
- Succesrespons: tuple `(user_id, tenant_id, user_email)` -- tenant_id altijd een string
- Foutrespons: geen exceptions; veilige fallbacks op elke stap
- Uitzonderingen: --

---

## QA-checks

- [x] Aanwezigheid AuditLoggingMiddleware geverifieerd (unit test GROEN)
- [x] Architecture tests als regression guards GROEN
- [x] Pyright 0 errors na wijziging

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Trainingssamenvatting aanwezig
- [x] Review: zie review-BE-SEC-025.md
