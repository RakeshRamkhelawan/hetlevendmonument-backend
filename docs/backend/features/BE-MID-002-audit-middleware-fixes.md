# Backend Feature Specification

## Metadata

- Feature ID: BE-MID-002
- Feature naam: AuditLoggingMiddleware Defect Fixes & DB Integration
- Status: APPROVED
- Auteur: Antigravity
- Reviewer: Rakesh Ramkhelawan
- Datum: 2026-06-01
- Gerelateerde user story / ticket: SP-WE-14b
- Gerelateerde router / module: `src/core/middleware/audit_middleware.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: `request_audit_logs`
- Versie: 1.0

---

## Doel en scope

### Doel

Herstellen van drie kritieke defecten (P0) in de `AuditLoggingMiddleware` om database-logging via de async session factory correct te laten verlopen met type-isolatie en robuuste foutafhandeling.

### In scope

- Alembic-migratie toevoegen voor `request_audit_logs` (NEW-SEC-002) met RLS.
- `db_session_factory` configureren met `get_db_session` in `middleware_config.py` (NEW-SEC-001).
- Type mismatch oplossen van `tenant_id` van integer naar String(50) door middel van een string cast (CG-008).
- Foutstatus mapping van "ERROR" naar `500` bij uitzonderingen in database logging.
- `best_effort` foutafhandeling voor database logging.

### Out of scope

- Drift op `workflow_executions` indexen herstellen (valt onder `NEW-DATA-001`).

---

## Build summary

- Nieuw gebouwd: Alembic-migratie `3ee55ea8e623_add_request_audit_logs.py`.
- Gewijzigd:
  - `src/core/middleware/audit_middleware.py` (implementatie van `_write_to_db`, type-casts, timing van extractie).
  - `src/core/api/setup/middleware_config.py` (wijzen van `get_db_session` naar `db_session_factory`).
  - `src/core/database/import_all_models.py` (registratie van `RequestAuditLog` model).
- Verwijderd: Geen.
- Beinvloede bestaande flows: API request en response audit log flow.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MID-002 | AuditLoggingMiddleware | Middleware | `src/core/middleware/audit_middleware.py` | Wijziging | Request & Response Audit Trail |
| BE-MIG-009 | Alembic Migration for request_audit_logs | Alembic-migratie | `src/alembic/versions/3ee55ea8e623_add_request_audit_logs.py` | Nieuw | Database Schema Setup |

---

## API-flows

### Flow ID: BE-FLW-006

- Naam: Request/Response Database Audit Logging
- Trigger (HTTP-methode + route of event): Elke HTTP-aanroep (behalve uitgesloten paden zoals `/health`).
- Voorwaarden (auth, tenant, feature flag): Geen specifieke voorwaarden. Werkt voor zowel anonieme als geauthenticeerde verzoeken.
- Request-pad:
  1. Request komt binnen.
  2. Middleware genereert request ID en start timer.
  3. Request wordt doorgestuurd naar de applicatie.
  4. Response wordt gegenereerd (of exception treedt op).
  5. Gebruikersinformatie (`user_id`, `tenant_id`, `user_email`) wordt geëxtraheerd uit `request.state`.
  6. Audit entry wordt opgebouwd.
  7. Audit log wordt naar stdout geschreven.
  8. Audit log wordt naar database weggeschreven via `best_effort`.
  9. Response wordt geretourneerd met `X-Request-ID` header (of exception wordt doorgegooid).
- Service-stappen:
  - `_extract_user_info(request)` voor veilige extractie van user en tenant metadata (voorkomt Mock lekken).
  - `_write_to_db(audit_entry)` voor async database persistence.
- DB-operaties: `session.add(RequestAuditLog)` en `session.commit()`.
- Successtatus + response: Originele response + `X-Request-ID` header.
- Foutpaden: Database-fouten tijdens het loggen worden opgevangen door `best_effort` en beïnvloeden de hoofdrespons niet. Exception in de hoofdapplicatie resulteert in een status_code `500` audit log en de exception wordt opnieuw gegooid.
- Eindtoestand (DB, cache, events): Nieuw record in `request_audit_logs`.

---

## Detaildocumentatie per artefact

## [BE-MID-002] AuditLoggingMiddleware

### 1. Type

Middleware

### 2. Locatie

- Bestandspad: `src/core/middleware/audit_middleware.py`
- Klasse / functie: `AuditLoggingMiddleware`

### 3. Gerelateerde flow

BE-FLW-006

### 4. Doel

Automatisch en niet-blokkerend auditeren van alle inkomende API-verzoeken, inclusief authenticatie- en tenantsleutels, verwerkingstijd en response-status.

### 5. Functionele beschrijving

De middleware registreert elk inkomend en uitgaand verzoek op het platform. Dit dient voor compliancy (AVG/GDPR en AI Act) en debugging. Er wordt bijgehouden welke gebruiker (indien ingelogd) welke actie heeft uitgevoerd op welke resource, wat de statuscode was en hoe snel dit is afgehandeld. Dit gebeurt op de achtergrond zonder dat de gebruiker vertraging oploopt.

### 6. Technische beschrijving

De middleware erft van Starlette's `BaseHTTPMiddleware`. Tijdens de dispatch-cyclus:
1. Paden zoals `/health`, `/metrics`, etc. worden overgeslagen.
2. Een unieke UUID4 request ID wordt gegenereerd en aan `request.state` toegevoegd.
3. De starttijd wordt gemeten met `time.perf_counter()`.
4. De applicatie verwerkt de request.
5. In de `try`- en `except`-blokken wordt de verwerkingstijd berekend en de gebruikersinformatie geëxtraheerd via `self._extract_user_info(request)`.
6. Een `RequestAuditLog` SQLAlchemy model wordt aangemaakt.
7. Als `self.log_to_db` en `self.db_session_factory` zijn ingesteld, wordt de database-write uitgevoerd via `self._write_to_db()`.
8. Dit schrijven is verpakt in `best_effort`, waardoor fouten in de database (bijv. timeout of down state) de API-respons niet verstoren.
9. De response wordt voorzien van de header `X-Request-ID`.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Geen (anonieme requests worden ook gelogd met `user_id = None`).
- Vereiste rol / scope: Alle.
- Tenant-isolatie: Audit logs worden weggeschreven met `tenant_id`. De tabel `request_audit_logs` is beveiligd met Row-Level Security (RLS) om te garanderen dat tenants alleen hun eigen audit logs kunnen inzien.
- Feature flag: `log_to_db` parameter (gekoppeld aan `ENVIRONMENT == "production"`).

### 8. Request-specificatie

- Methode: Alle HTTP-methoden.
- Route: Alle applicatie-routes (behalve `EXCLUDED_PATHS`).
- Path parameters: Geen (wordt geëxtraheerd uit het pad voor metadata).
- Query parameters: Geen (wordt gemaskeerd opgeslagen).
- Request body (schema): Geen.
- Verplichte headers: Geen.

### 9. Response-specificatie

- Successtatus: Ongewijzigd, voegt `X-Request-ID` toe.
- Response schema: Ongewijzigd.
- Foutstatussen: Ongewijzigd (middleware logt "ERROR" status als 500 naar database).

### 10. Validaties en constraints

- `tenant_id` wordt gecast naar `str` (maximaal 50 karakters) om type mismatches te voorkomen.
- Gevoelige query parameters (wachtwoorden, tokens) worden gemaskeerd met `[REDACTED]`.

### 11. Business rules

- Audit trail mag nooit verloren gaan, maar mag de live-operatie niet platleggen (vandaar `best_effort`).
- Status codes die als `"ERROR"` (bij exceptions) binnenkomen worden in de database als `500` gelogd.

### 12. Afhankelijkheden

- `get_db_session` uit `src/core/database/session.py` (voor async database sessies).
- `best_effort` uit `src/core/utils/best_effort.py` (voor veilige foutafhandeling).

### 13. Foutafhandeling

Fouten tijdens het wegschrijven naar de database worden door `best_effort` afgevangen, gelogd naar stdout/stderr via `logger.error`, en niet doorgegooid naar de gebruiker.

### 14. Transacties en dataïntegriteit

De database-sessie voert een `commit()` uit na het toevoegen van het record om de data direct persistent te maken.

### 15. Telemetry / logging / tracing

- Logs worden geschreven naar `logger.info` (AUDIT) en `logger.error` (AUDIT_ERROR) in een gestandaardiseerd formaat inclusief `extra` metadata voor log-aggregators (Jaeger/Grafana).

### 16. Caching

- Gecached: Nee.

### 17. Acceptatiecriteria

- [x] Middleware moet geconfigureerd zijn met een geldige async database session factory (`get_db_session`).
- [x] Tabel `request_audit_logs` moet bestaan in de database en een geldige Alembic migratie-head hebben.
- [x] `tenant_id` geleverd als integer of string moet correct worden opgeslagen als string (String(50)) zonder database crashes.
- [x] Bij exceptions in de request-afhandeling moet de statuscode als `500` worden opgeslagen in de database.
- [x] Fouten in de database-logging mogen de API response niet beïnvloeden (`best_effort` garantie).

### 18. Integratoruitleg

- Elk API-verzoek krijgt een unieke header `X-Request-ID` teruggestuurd.
- Gebruik deze `X-Request-ID` bij support-vragen om specifieke verzoeken in de audit logs terug te vinden.
- Gevoelige data (zoals tokens en wachtwoorden in query-parameters) wordt automatisch gemaskeerd in de logs.

### 19. Trainingssamenvatting

- Actor: API Client
- Voorwaarde: API endpoint is geregistreerd en middleware is actief.
- Actie (request): HTTP request naar een endpoint.
- Systeemverwerking: Verzoek wordt afgehandeld, metadata wordt geëxtraheerd en via `best_effort` weggeschreven naar `request_audit_logs`.
- Succesrespons: HTTP response met `X-Request-ID` header.
- Foutrespons: HTTP foutrespons (bijv. 500) indien applicatie faalt, met correcte audit log registratie.
- Uitzonderingen: Database offline -> audit log faalt stil (gelogd naar logger), API response slaagt nog steeds.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- De middleware is transparant en vereist geen aanpassingen van client-zijde.
- Bewaar en log de `X-Request-ID` header die in elke response zit. Dit vergemakkelijkt auditing en incident response aanzienlijk.

---

## Open aannames

Geen.

---

## Open vragen

Geen.

---

## Risico's

- Hoge database-belasting: Aangezien elke request een database write uitvoert in productie, kan dit bij zeer hoge volumes leiden tot database I/O bottlenecks. Dit risico wordt gematigd door async execution en `best_effort`.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (leeg, null, grenzen)
- [x] Dataïntegriteit en transacties getest
- [x] Logging en tracing gecontroleerd

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
