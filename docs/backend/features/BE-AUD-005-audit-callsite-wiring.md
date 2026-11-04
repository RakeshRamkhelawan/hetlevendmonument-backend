# Backend Feature Specification

## Metadata

- Feature ID: BE-AUD-005
- Feature naam: session=db wiring voor alle log_action() call-sites (15 call-sites, 7 bestanden)
- Status: APPROVED
- Auteur: AI-agent (SP-AUDIT-004)
- Reviewer: BE-review-agent
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-AUDIT-004
- Gerelateerde router / module: user_management, tenant_management, documents, notifications
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: audit_logs
- Versie: 1.0

---

## Doel en scope

### Doel

Zorgt dat elke `log_action()` aanroep in alle router-bestanden de huidige database-db
meekrijgt via `session=db`. Zonder db retourneert `log_action()` stilzwijgend None
zonder enige DB-write -- een silent ADR-019 schending.

### In scope

- Toevoegen van `session=db` aan 15 log_action()-aanroepen in 7 bestanden
- Toevoegen van `db_session=db` aan 9 best_effort()-aanroepen die dat nog misten
- Herordenen van audit na primaire DB-operatie in delete_user en delete_tenant

### Out of scope

- Wijzigingen aan log_action() zelf (gedekt door BE-AUD-003)
- Wijzigingen aan callers buiten de 7 genoemde bestanden
- Domains/verticals (nonprofit.py, media.py, healthcare.py) -- apart backlog-item

---

## Build summary

- Nieuw gebouwd: n.v.t.
- Gewijzigd: 7 bestanden (zie inventory)
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: alle CRUD-operaties op users, tenants, documents, notifications

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AUD-005a | user_management/crud_router log_action wiring | BE-RTR | src/core/api/v1/user_management/crud_router.py | Wijziging | User CRUD flows |
| BE-AUD-005b | user_management/profile_router log_action wiring | BE-RTR | src/core/api/v1/user_management/profile_router.py | Wijziging | User status flow |
| BE-AUD-005c | documents/crud_router log_action wiring | BE-RTR | src/core/api/v1/documents/crud_router.py | Wijziging | Document CRUD flows |
| BE-AUD-005d | documents/processing_router log_action wiring | BE-RTR | src/core/api/v1/documents/processing_router.py | Wijziging | Document processing flow |
| BE-AUD-005e | documents/upload_router log_action wiring | BE-RTR | src/core/api/v1/documents/upload_router.py | Wijziging | Document upload flow |
| BE-AUD-005f | notifications/router log_action wiring | BE-RTR | src/core/api/v1/notifications/router.py | Wijziging | Notification read flows |
| BE-AUD-005g | tenant_management/crud_router log_action wiring | BE-RTR | src/core/api/v1/tenant_management/crud_router.py | Wijziging | Tenant CRUD flows |

---

## API-flows

### Flow: Audit-logging na primaire DB-operatie (correct patroon)

- Naam: Audit na commit
- Trigger: Elke write-operatie (create, update, delete) op users/tenants/documents/notifications
- Voorwaarden: Primaire DB-operatie succesvol afgerond (commit gedaan)
- Request-pad: endpoint -> primaire DB-operatie -> db.commit() -> best_effort(db_session=db) -> log_action(session=db)
- Service-stappen:
  1. Primaire write (INSERT/UPDATE/DELETE) + db.commit()
  2. best_effort context openen met db_session=db
  3. log_action() aanroepen met session=db
  4. log_action() voegt AuditLog toe aan db (db.add())
  5. get_db() auto-commit na request-einde persisteert de audit entry
- DB-operaties: db.add(AuditLog) -- geen expliciete commit nodig (get_db() doet dit)
- Successtatus + response: AuditLog object (intern); caller-endpoint retourneert zijn eigen response
- Foutpaden: als log_action() faalt, vangt best_effort de exception op en rollback (primaire data veilig)
- Eindtoestand: primaire data gecommittet + audit entry in db (pending commit na request)

### Flow: delete_user en delete_tenant ordering fix

- Naam: Audit na hard-delete
- Trigger: DELETE aanroep op user of tenant
- Bijzonderheid: user-object is niet meer beschikbaar na db.delete() + db.commit()
- Herordening: audit wordt NADAT de delete is gecommittet uitgevoerd
- Gebruik van `user_id` (function parameter) ipv `user.id` (ORM attribute -- expired na commit)

---

## Detaildocumentatie per artefact

## [BE-AUD-005] log_action() callsite wiring -- samenvattend

### 1. Type

- Pattern fix over meerdere router-bestanden

### 2. Locatie

- 7 bestanden (zie inventory)

### 3. Gerelateerde flow

- Alle write-flows in user_management, tenant_management, documents, notifications

### 4. Doel

- Garandeert dat elke log_action()-aanroep een geldige database-db ontvangt zodat de audit entry daadwerkelijk naar de DB geschreven wordt

### 5. Functionele beschrijving

- Voor fix: `log_action()` werd aangeroepen zonder `session=db` -- stilzwijgend None return, geen audit entry in DB
- Na fix: `log_action()` wordt altijd aangeroepen met `session=db` -- AuditLog wordt via `db.add()` aan de db toegevoegd en na het request gecommittet door `get_db()` auto-commit

### 6. Technische beschrijving

Patroon na fix (per call-site):
```python
async with best_effort("beschrijving", db_session=db):
    await audit_service.log_action(
        tenant_id=...,
        action="...",
        resource="...",
        session=db,
    )
```

- `best_effort(db_session=db)`: rollback-guard -- als log_action faalt, wordt de db teruggerold (geen half-aangepaste state)
- `session=db`: de huidige request-db; `get_db()` auto-commit (database.py:489) persisteert de pending db.add() na het request
- Geen expliciete `await db.commit()` nodig binnen best_effort

**delete_user herordening:**
```python
# VOOR (fout): audit VOOR delete
async with best_effort("user.deleted audit log"):
    await audit_service.log_action(...)
await db.delete(user)
await db.commit()

# NA (correct): audit NA delete
await db.delete(user)
await db.commit()
async with best_effort("user.deleted audit log", db_session=db):
    await audit_service.log_action(
        resource=f"user:{user_id}",  # gebruik function parameter, niet user.id (expired)
        session=db,
    )
```

**delete_tenant herordening:** identiek patroon -- audit na `tenant.is_active = False` + `db.commit()`

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: afgedwongen door bestaande router guards (JWT + tenant context)
- Tenant-isolatie: tenant_id wordt uit JWT middleware gehaald (niet uit request body)

### 8. Request-specificatie

- Methode: n.v.t. (pattern fix over bestaande endpoints)
- Impact per endpoint: geen wijziging in request/response interface

### 9. Response-specificatie

- Geen wijziging in response schemas of statuscodes

### 10. Validaties en constraints

- Na delete: ORM-attributes zijn expired; gebruik function parameters (user_id, tenant_id) ipv ORM-attributes
- db_session=db in best_effort: rollback-guard actief alleen voor audit-db mutations

### 11. Business rules

- ADR-019: elke write-operatie moet een audit entry produceren in de DB
- ADR-019: audit logging is best-effort (mag primaire request niet blokkeren)
- Audit entry na primaire commit: garandeert dat audit refereert aan gecommittete data

### 12. Afhankelijkheden

- `src/core/utils/best_effort.py`: best_effort context manager
- `src/core/governance/audit.py`: AuditService.log_action()
- `src/core/database.py`: get_db() auto-commit op line 489

### 13. Foutafhandeling

- Als log_action() een exception gooit: best_effort logt de fout en rollback db; primaire response wordt normaal teruggegeven
- Als db (db) ongeldig is: best_effort vangt de exception op

### 14. Transacties en dataintegritiet

- Primaire commit (bijv. db.delete(user) + db.commit()) is afgerond voor de audit
- Audit entry is een aparte db.add() -- pending in de db na het commit
- get_db() auto-commit na request-einde: audit entry wordt persistent

### 15. Telemetry / logging / tracing

- best_effort logt bij falen: `logger.error("best_effort: ... audit log", exc_info=True)`
- Geen extra logging toegevoegd (bestaand patroon)

### 16. Caching

- n.v.t.

### 17. Acceptatiecriteria

- Elke log_action()-aanroep in de 7 bestanden bevat `session=db`
- Elke best_effort()-aanroep in de 7 bestanden bevat `db_session=db`
- delete_user: audit na db.delete(user) + db.commit()
- delete_tenant: audit na tenant.is_active = False + db.commit()
- resource=f"user:{user_id}" (function parameter) ipv user.id in delete_user
- resource=f"tenant:{tenant_id}" (function parameter) ipv tenant.id in delete_tenant
- Architecture test `test_log_action_calls_have_session` GROEN voor alle 7 bestanden

### 18. Integratoruitleg

- Geen wijziging in API interface of response format
- Audit entries zijn nu betrouwbaar aanwezig in audit_logs tabel na elke write-operatie

### 19. Trainingssamenvatting

- Actor: admin of geldige gebruiker die een write-operatie uitvoert
- Voorwaarde: geldige JWT + voldoende permissies + geldige tenant context
- Actie: bijv. POST /api/v1/users/ (create user)
- Systeemverwerking: primaire write -> commit -> best_effort -> log_action(session=db) -> db.add(AuditLog)
- Succesrespons: endpoint response ongewijzigd; AuditLog gepersisteerd na request
- Foutrespons: als audit faalt: best_effort absorbeert; endpoint response ongewijzigd
- Uitzonderingen: delete-flows: audit na commit; resource-string gebruikt function parameter ipv ORM-attribute

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Geen wijziging in request/response format
- Audit trail is nu betrouwbaar; audit_logs tabel bevat records voor alle write-operaties
- Forensisch gebruik: query audit_logs op action, tenant_id, user_id, timestamp

---

## Open aannames

- `get_db()` auto-commit op database.py:489 persisteert pending db.add() na request -- geverifieerd via tenants_list_router.py patroon
- Domains/verticals (nonprofit.py etc.) hebben nog geen db-DI; backlog-item voor volgende sprint

## Open vragen

- n.v.t.

## Risico's

- Laag: herordening delete_user/delete_tenant gebruikt function parameters; ORM-attribute expiration na commit is een bekende SQLAlchemy gotcha die nu correct is afgehandeld

---

## QA-checks

- [x] Architecture test groen voor alle 7 bestanden
- [x] Happy path: audit entry aanwezig na write-operatie
- [x] Delete-flow: audit na commit
- [x] best_effort absorbeert audit-falen zonder response-impact
- [x] tenant_id uit middleware (niet request body)
- [x] Regressietest: 793 tests GROEN na wijziging

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Foutstatussen beschreven
- [x] Functionele en technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
- [x] QA-checks uitgevoerd
- [x] Review: APPROVED
