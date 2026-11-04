# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-015
- Feature naam: /api/v1/notifications REST Endpoints
- Status: READY
- Auteur: Antigravity AI
- Reviewer: code-reviewer, quality-reviewer
- Datum: 2026-05-31
- Gerelateerde user story / ticket: SP-WE-02 Dag 3 (WE-012/013/014)
- Gerelateerde router / module: `src/core/api/v1/notifications/router.py`
- Gerelateerde frontend endpoints: `/api/v1/notifications`, `/api/v1/notifications/mark-all-read`, `/api/v1/notifications/{id}/read`
- Gerelateerde database tabellen: `notifications`
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een REST API voor het inzien en beheren (lezen / markeren als gelezen) van in-app notificaties in de inbox van de gebruiker. Dit is strict tenant-isolated en ondersteunt paginering.

### In scope

- `GET /api/v1/notifications` paginering en filters (ongelezen).
- `POST /api/v1/notifications/mark-all-read` bulk markering.
- `POST /api/v1/notifications/{id}/read` markeren van een specifieke notificatie.
- Strict tenant-isolatie (verifieert `tenant_id` JWT claims tegen database records).
- `best_effort` logging van audits.

### Out of scope

- Push notificaties (zoals APNS, FCM of e-mail dispatchers). Dit is puur voor de database-backed in-app inbox.

---

## Build summary

- Nieuw gebouwd:
  - Notifications REST router in [router.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/api/v1/notifications/router.py)
  - Pydantic validatieschema's in [schemas.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/api/v1/notifications/schemas.py)
  - Unit/Integratietests in [test_sp_we_02_notifications_router.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/tests/unit/test_sp_we_02_notifications_router.py)
- Gewijzigd:
  - `Notification` ORM model in [models.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/domains/notifications/models.py) (SQLite-compatibele CURRENT_TIMESTAMP default)
  - Centrale router registry [router_registry.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/api/router_registry.py) (registreert notifications router)
- Verwijderd:
  - N/A

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-015 | `/api/v1/notifications` | REST API Endpoints | `src/core/api/v1/notifications/router.py` | Nieuw | BE-FLW-004 |

---

## API-flows

### Flow ID: BE-FLW-004

- Naam: Gebruiker beheert notificaties inbox
- Trigger (HTTP-methode + route of event): `GET /api/v1/notifications` of `POST /api/v1/notifications/...`
- Voorwaarden (auth, tenant, feature flag): Geldig JWT access token met correcte `tenant_id`
- Request-pad: Browser -> `/api/v1/notifications` -> JWT extractie -> Route handler
- Service-stappen:
  1. Extraheert `current_user` en `tenant_id`
  2. Valideert tenant match (JWT tenant_id vs request context)
  3. Voert de database query/update uit met SQL filter op `tenant_id` en `user_id`
  4. Genereert audit log via `best_effort`
- DB-operaties: SELECT / UPDATE op `notifications` tabel
- Successtatus + response: `200 OK` met JSON envelop `{"success": true, "data": ...}`
- Foutpaden:
  - 401 Unauthorized (ontbrekende token)
  - 403 Forbidden (tenant mismatch)
  - 404 Not Found (indien notificatie van andere tenant/user)
- Eindtoestand (DB, cache, events): Notificatiestatus `is_read` bijgewerkt in DB.

---

## Detaildocumentatie per artefact

## [BE-EP-015] /api/v1/notifications

### 1. Type

- REST API Endpoints

### 2. Locatie

- Bestandspad: `src/core/api/v1/notifications/router.py`
- Klasse / functie: `list_notifications`, `mark_all_read`, `mark_as_read`

### 3. Gerelateerde flow

- BE-FLW-004

### 4. Doel

- Inbox beheer en notificatie-overzicht voor SaaS gebruikers.

### 5. Functionele beschrijving

- Gebruikers kunnen hun ongelezen notificaties ophalen en individueel of in bulk markeren als gelezen. Alle acties zijn strikt beveiligd zodat men nooit notificaties van andere tenants of andere gebruikers kan inzien of manipuleren.

### 6. Technische beschrijving

- Maakt gebruik van SQLAlchemy's async `select` queries met filters `where(Notification.tenant_id == tenant_id, Notification.user_id == user_id)`.
- Pagining via `limit` (max 100) en `offset` query parameters.
- Maakt gebruik van `best_effort` helper bij het aanroepen van `audit_service.log_action` om database timeouts op de audit logs te isoleren van de hoofdtransactie.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja, JWT token.
- Vereiste rol / scope: Geldige user.
- Tenant-isolatie: Strikte database-niveau RLS en expliciete query filters.
- Feature flag: N/A

### 8. Request-specificatie

- Methode: GET / POST
- Route: `/api/v1/notifications`
- Path parameters: `notification_id` (bij mark_as_read)
- Query parameters: `limit`, `offset`, `unread_only`
- Request body (schema): N/A
- Verplichte headers: `Authorization: Bearer <token>` of `Cookie`.

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `NotificationListResponse` of `NotificationResponse`
- Foutstatussen: 401, 403, 404, 422, 500

### 10. Validaties en constraints

- `limit` moet tussen 1 en 100 liggen. `offset` moet >= 0 zijn.

### 11. Business rules

- Bij het markeren als gelezen wordt `is_read` op True gezet en `read_at` ingesteld op de huidige UTC tijd.

### 12. Afhankelijkheden

- SQLAlchemy AsyncSession, current_user dependency, AuditService.

### 13. Foutafhandeling

- Foutieve ids of ids van andere tenants retourneren een `404 Not Found`.

### 14. Transacties en dataïntegriteit

- Updates worden binnen een transactie uitgevoerd. Bij fouten vindt automatische rollback plaats.

### 15. Telemetry / logging / tracing

- Audit events: `notification.mark_read` en `notification.mark_all_read`.

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- [x] Paginering werkt correct via `limit` en `offset`.
- [x] Alleen notificaties behorend tot de geauthenticeerde user/tenant worden getoond.
- [x] Pogingen om notificaties van andere tenants te wijzigen geeft 404.
- [x] Audit logs falen nooit de primaire database commits.

### 18. Integratoruitleg

- Vraag notificaties op via `GET /api/v1/notifications?limit=20&unread_only=true`.
- Markeer een notificatie als gelezen met `POST /api/v1/notifications/{id}/read`.

### 19. Trainingssamenvatting

- Actor: SaaS Gebruiker
- Voorwaarde: Ingelogd, notificaties aanwezig
- Actie (request): GET `/api/v1/notifications`
- Systeemverwerking: Query filtert op user en tenant, returned lijst
- Succesrespons: 200 OK + data lijst
- Foutrespons: 401 Unauthorized / 403 Tenant mismatch.

---

## Open aannames

- De tabel `notifications` is correct gemigreerd via eerdere Alembic versies.

## Open vragen

- Geen.

## Risico's

- N/A

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
- [x] Alle endpoints, services en modellen zijn geïnventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED
