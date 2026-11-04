# Backend Feature Specification -- BE-MID-001: AuditLoggingMiddleware ASGI Wiring

## Metadata

- **Feature ID:** BE-MID-001
- **Feature naam:** AuditLoggingMiddleware ASGI Wiring
- **Status:** APPROVED
- **Auteur:** Gemini CLI
- **Reviewer:** Gemini CLI
- **Datum:** 2026-06-01
- **Gerelateerde user story / ticket:** SP-WE-14 (CG-008)
- **Gerelateerde router / module:** `src/core/api/setup/middleware_config.py`
- **Gerelateerde database tabellen:** `request_audit_logs` (schema aanwezig, write post-MVP)
- **Versie:** 1.0

---

## Doel en scope

### Doel

Registreren van de `AuditLoggingMiddleware` in de ASGI stack om request-level audit logging te activeren voor alle mutaties en gevoelige endpoints, conform ADR-019 en SOC 2 CC7.2.

### In scope

- Opschonen van `src/core/middleware/audit_middleware.py` (f-string fixes, PII masking).
- Registratie van `AuditLoggingMiddleware` in `src/core/api/setup/middleware_config.py`.
- Correcte LIFO positionering (na Prometheus, voor TenantMiddleware).
- Unit tests voor de middleware functionaliteit.

### Out of scope

- Implementatie van asynchrone database-writes voor audit logs (gepland voor post-MVP).
- Wijzigingen aan de `RequestAuditLog` SQLAlchemy model definitie.

---

## Build summary

- **Nieuw gebouwd:** Unit test suite `tests/unit/test_audit_logging_middleware.py`.
- **Gewijzigd:**
    - `src/core/middleware/audit_middleware.py`: PII masking, logging format verbeteringen.
    - `src/core/api/setup/middleware_config.py`: Middleware registratie en layer reordering.
- **Verwijderd:** Geen.
- **Beinvloede bestaande flows:** API Request flow (alle endpoints behalve excluded paths).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MID-001 | AuditLoggingMiddleware | BE-MID | `src/core/middleware/audit_middleware.py` | Wijziging | BE-FLW-001 |

---

## API-flows

### Flow ID: BE-FLW-001: API Request Audit Logging

- **Naam:** API Request Audit Logging
- **Trigger:** Inkomende HTTP request naar de ASGI stack.
- **Voorwaarden:** Path niet in `EXCLUDED_PATHS`.
- **Request-path:** Alle API endpoints (bijv. `/api/v1/missions`).
- **Service-stappen:**
    1. `AuditLoggingMiddleware` genereert `request_id`.
    2. `TenantMiddleware` (outer) zet user context.
    3. Handler verwerkt request.
    4. `AuditLoggingMiddleware` vangt response, berekent tijd.
    5. Log entry geschreven naar stdout (zonder PII).
    6. `X-Request-ID` header toegevoegd aan response.
- **DB-operaties:** Geen in Dag 1 (`log_to_db=False`).
- **Successtatus + response:** Originele response + `X-Request-ID` header.
- **Foutpaden:** Exception in handler wordt gelogd als `AUDIT_ERROR` en re-raised.
- **Eindtoestand:** Request is gelogd, client heeft tracking ID.

---

## Detaildocumentatie per artefact

---

## [BE-MID-001] AuditLoggingMiddleware

### 1. Type

- BE-MID (Middleware)

### 2. Locatie

- **Bestandspad:** `src/core/middleware/audit_middleware.py`
- **Klasse / functie:** `AuditLoggingMiddleware`

### 3. Gerelateerde flow

- BE-FLW-001

### 4. Doel

Zorgen voor onweerlegbare logging van alle API interacties voor compliance doeleinden.

### 5. Functionele beschrijving

De middleware houdt bij wie (user_id/tenant_id), wat (method/path/action), wanneer (timestamp) en hoe snel (response_time_ms) een request is afgehandeld. Het maskeert gevoelige data in query parameters en voorkomt dat e-mailadressen in de standaard server logs verschijnen.

### 6. Technische beschrijving

- Gebruikt `BaseHTTPMiddleware` van Starlette.
- Maskeert parameters zoals `token`, `password`, `api_key` via `_mask_query_params`.
- Gebruikt `request.state.user` (gezet door `TenantMiddleware`) voor context.
- Voegt `X-Request-ID` toe aan zowel de inkomende request state als de uitgaande response headers.
- Voldoet aan CLAUDE.md §11 (geen f-strings in logs, gebruik van `extra` velden).

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** Werkt voor zowel authenticated als unauthenticated requests (user_id=None).
- **Tenant-isolatie:** Logt `tenant_id` indien beschikbaar in de context.

### 8. Request-specificatie

N.v.t. (Middleware)

### 9. Response-specificatie

- **Extra headers:** `X-Request-ID` (UUID4).

### 10. Validaties en constraints

- PII mag niet gelogd worden naar stdout.
- Audit logging mag de primaire flow niet blokkeren (graceful failure).

### 11. Business rules

Conform ADR-019 en SOC 2 CC7.2.

### 12. Afhankelijkheden

- `TenantMiddleware` (voor user context).
- `PrometheusMiddleware` (voor timing metrics).

### 13. Foutafhandeling

- Exceptions in de handler worden gelogd en re-raised.
- Toekomstige DB writes moeten via `best_effort` verlopen.

### 14. Transacties en dataïntegriteit

N.v.t. (Dag 1).

### 15. Telemetry / logging / tracing

- **Log prefix:** `AUDIT` of `AUDIT_ERROR`.
- **Log attributes:** method, path, status, timing, tenant_id, user_id, request_id.

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [x] Middleware geregistreerd in `setup_middleware()`.
- [x] LIFO positie correct (Tenant -> Audit -> Prometheus).
- [x] Geen f-strings in logger aanroepen.
- [x] Query parameters met `token` of `password` zijn gemaskeerd.
- [x] `X-Request-ID` header aanwezig in response.

### 18. Integratoruitleg

Gebruik de `X-Request-ID` header in support-tickets om specifieke requests terug te vinden in de logs.

### 19. Trainingssamenvatting

- **Actor:** API Client.
- **Voorwaarde:** Request naar beveiligd endpoint.
- **Actie (request):** POST request met gevoelige data.
- **Systeemverwerking:** Middleware genereert ID, handler verwerkt, middleware logt resultaat.
- **Succesrespons:** HTTP 200 + X-Request-ID.
- **Foutrespons:** HTTP 500 gelogd met stacktrace.
- **Uitzonderingen:** Excluded paths (health/metrics).

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Alle API responses bevatten nu een `X-Request-ID`.
- Bij foutmeldingen (4xx/500) dient dit ID meegestuurd te worden bij supportaanvragen.

---

## QA-checks

- [x] Endpoint functioneel getest (via `TestClient`).
- [x] Alle foutstatus-codes getest (Simulated exceptions).
- [x] Auth en permissies getest (User context logging).
- [x] Tenant-isolatie getest (Tenant ID logging).
- [x] Validaties getest (Masking logic).
- [x] Edge cases getest (Excluded paths).
- [x] Dataïntegriteit en transacties getest (N.v.t.).
- [x] Logging en tracing gecontroleerd (Stdout output verificatie).

---

## Definition of Done

- [x] Feature is gebouwd.
- [x] Alle endpoints, services en modellen zijn geinventariseerd.
- [x] Alle relevante foutstatussen zijn beschreven.
- [x] Functionele beschrijving aanwezig.
- [x] Technische beschrijving aanwezig.
- [x] Acceptatiecriteria zijn testbaar.
- [x] Integratoruitleg is aanwezig.
- [x] Trainingssamenvatting is aanwezig.
- [x] Open aannames zijn benoemd.
- [x] QA-checks zijn uitgevoerd.
- [x] Review door reviewer-prompt: APPROVED.
