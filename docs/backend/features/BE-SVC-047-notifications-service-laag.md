# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-047
- Feature naam: Notifications service-laag (ADR-033)
- Status: DONE
- Auteur: Claude (S1 sprint)
- Reviewer: Zie review/review-BE-SVC-047.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: AUDIT-DB-05
- Gerelateerde router / module: src/core/api/v1/notifications/
- Gerelateerde frontend endpoints: /notifications
- Gerelateerde database tabellen: notifications
- Versie: 1.0

---

## Doel en scope

### Doel

De notifications router bevatte directe SQLAlchemy imports en inline queries. ADR-033 vereist dat router.py geen directe DB-imports bevat. Deze sprint introduceert `NotificationsService` en een service factory in `dependencies.py`.

### In scope

- `src/core/api/v1/notifications/service.py` -- NotificationsService klasse
- `src/core/api/v1/notifications/dependencies.py` -- service factory
- `src/core/api/v1/notifications/router.py` -- rewrite zonder directe DB-imports

### Out of scope

- Wijzigingen aan Notification ORM model
- Push notifications
- Email notifications

---

## Build summary

- Nieuw gebouwd: service.py (NotificationsService), dependencies.py update
- Gewijzigd: router.py (inline SQL verwijderd)
- Verwijderd: directe imports van AsyncSession, get_db, select, func, update in router.py
- Beinvloede bestaande flows: GET /notifications, POST /notifications/mark-all-read, POST /notifications/{id}/read

---

## Backend inventory

| ID         | Naam                      | Type                    | Bestandspad                                   | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | ------------------------- | ----------------------- | --------------------------------------------- | --------------- | ----------------- |
| BE-SVC-047 | NotificationsService      | Service klasse          | src/core/api/v1/notifications/service.py      | Nieuw           | BE-FLW-047        |
| BE-DEP-047 | get_notifications_service | FastAPI Depends factory | src/core/api/v1/notifications/dependencies.py | Nieuw           | BE-FLW-047        |
| BE-RTR-047 | Notifications Router      | APIRouter               | src/core/api/v1/notifications/router.py       | Wijziging       | BE-FLW-047        |

---

## API-flows

### Flow ID: BE-FLW-047

- Naam: Notifications CRUD via service-laag
- Trigger: HTTP GET/POST naar /notifications/\*
- Voorwaarden: Geldige JWT; tenant_id en user_id uit JWT
- Request-pad: Request -> router.py -> Depends(get_notifications_service) -> NotificationsService
- Service-stappen: 1) Auth via get_current_user, 2) NotificationsService(db, tenant_id, user_id), 3) Service voert query uit met tenant_id + user_id filter
- DB-operaties: SELECT/UPDATE op notifications tabel; beide met tenant_id AND user_id filter
- Successtatus: 200 OK (list/mark) met JSON payload
- Foutpaden: 401 (geen token), 404 (notificatie niet gevonden), 422 (validatiefout), 500 (DB fout)
- Eindtoestand: is_read=True + read_at=now() na mark-operaties

---

## Detaildocumentatie per artefact

---

## [BE-SVC-047] NotificationsService

### 1. Type

- Service klasse

### 2. Locatie

- Bestandspad: src/core/api/v1/notifications/service.py
- Klasse / functie: NotificationsService

### 3. Gerelateerde flow

- BE-FLW-047

### 4. Doel

- Encapsuleert alle DB-toegang voor de notifications router; garandeert tenant+user isolatie op elke query

### 5. Functionele beschrijving

- `list_notifications(limit, offset, unread_only)`: geeft gepagineerde lijst van notificaties voor de huidige user en tenant. Optioneel gefilterd op ongelezen.
- `mark_all_read()`: zet alle ongelezen notificaties van de user op is_read=True, retourneert count.
- `mark_single_read(notification_id)`: zet 1 specifieke notificatie op gelezen; retourneert None als niet gevonden (router geeft dan 404).

### 6. Technische beschrijving

- Constructor: `__init__(db: AsyncSession, tenant_id: int, user_id: int)`
- Alle queries filteren op `Notification.tenant_id == self.tenant_id AND Notification.user_id == self.user_id`
- `list_notifications`: subquery voor count, daarna offset/limit/order_by(created_at.desc())
- `mark_all_read`: bulk update via Python loop + commit; audit log via best_effort
- `mark_single_read`: scalar_one_or_none + commit + refresh + audit log via best_effort
- Tijdstempels via `datetime.now(timezone.utc)` (nooit datetime.now() zonder tz)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Bearer JWT (afgedwongen in factory)
- Vereiste rol / scope: Authenticated user
- Tenant-isolatie: tenant_id + user_id op elke query (dubbele isolatie)
- Feature flag: N/A

### 8. Request-specificatie

- Methode: GET /notifications, POST /notifications/mark-all-read, POST /notifications/{id}/read
- Path parameters: notification_id (integer, POST /{id}/read)
- Query parameters: limit (int, 1-100, default 20), offset (int, >=0), unread_only (bool)
- Request body (schema): Geen
- Verplichte headers: Authorization: Bearer <token>

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `{"success": true, "data": [...], "total": int, "limit": int, "offset": int}` (list); `{"success": true, "count": int}` (mark-all); `{"success": true, "data": NotificationResponse}` (mark-single)
- Foutstatussen: 401, 404 (mark-single), 422, 500

### 10. Validaties en constraints

- limit: 1-100; offset: >=0
- notification_id moet positief integer zijn
- Notificatie moet bij huidige tenant+user horen

### 11. Business rules

- Gebruiker ziet alleen eigen notificaties (user_id filter)
- Notificaties zijn tenant-gebonden (tenant_id filter)
- Reeds gelezen notificaties worden bij mark_single_read stilletjes geretourneerd (idempotent)

### 12. Afhankelijkheden

- src/domains/notifications/models.Notification
- src/core/governance/audit.audit_service
- src/core/utils/best_effort.best_effort

### 13. Foutafhandeling

- 400: N/A (validatie via FastAPI/Pydantic)
- 401: Factory gooit HTTPException via get_current_user
- 403: N/A (user_id filter geeft 404 bij verkeerde user)
- 404: mark_single_read retourneert None -> router geeft 404
- 409: N/A
- 422: Query parameter validatie via FastAPI
- 429: N/A (geen rate limit op dit endpoint)
- 500: DB-fout propageren als HTTPException(500)
- 503: N/A

### 14. Transacties en dataïntegriteit

- mark_all_read: commit na bulk update; audit log in best_effort (apart van primaire commit)
- mark_single_read: commit na single update; refresh na commit; audit log in best_effort

### 15. Telemetry / logging / tracing

- Audit log via audit_service.log_action bij mark-operaties
- OpenTelemetry spans via DB-laag

### 16. Caching

- Gecached: Nee
- Cache-sleutel: N/A
- TTL: N/A
- Invalidatie: N/A

### 17. Acceptatiecriteria

- [ ] GET /notifications retourneert gepagineerde lijst met correct total
- [ ] unread_only=true filtert alleen ongelezen notificaties
- [ ] POST /notifications/mark-all-read zet alle ongelezen op gelezen; retourneert count
- [ ] POST /notifications/{id}/read retourneert 404 voor onbekend id
- [ ] User A ziet notificaties van user B niet (user_id isolatie)
- [ ] Tenant A ziet notificaties van tenant B niet (tenant_id isolatie)
- [ ] router.py bevat geen import van AsyncSession, get_db, select, func

### 18. Integratoruitleg

- GET /notifications?limit=20&offset=0&unread_only=false -- paginated inbox
- POST /notifications/mark-all-read -- markeert alle unread als gelezen
- POST /notifications/{id}/read -- markeert 1 notificatie als gelezen (404 als niet gevonden)
- Alle endpoints vereisen Bearer JWT token

### 19. Trainingssamenvatting

- Actor: Authenticated user
- Voorwaarde: Geldig JWT token; notificaties aanwezig in DB voor die user+tenant
- Actie (request): GET of POST naar /notifications endpoints
- Systeemverwerking: Service filtert op tenant_id+user_id; commit bij writes; audit log in best_effort
- Succesrespons: 200 OK met data of count
- Foutrespons: 401 (geen auth), 404 (notificatie niet gevonden), 422 (ongeldige params)
- Uitzonderingen: Idempotente mark-single-read (reeds gelezen retourneert 200 zonder DB-write)

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Alle endpoints vereisen Authorization: Bearer <token>
- tenant_id en user_id worden automatisch uit het token gehaald
- unread_only=true voor inbox-badge count queries
- mark-all-read is idempotent: meerdere aanroepen zijn veilig

---

## Open aannames

- Notification model heeft: id, tenant_id, user_id, is_read, read_at, created_at velden

## Open vragen

- Geen

## Risico's

- N/A

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Edge cases getest (404, dubbele mark-read)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle services geinventariseerd
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
