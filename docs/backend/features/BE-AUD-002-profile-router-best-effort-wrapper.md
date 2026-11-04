# BE-AUD-002 -- profile_router.py update_user_status best_effort wrapper

**Sprint:** SP-AUDIT-003 Dag 2
**Datum:** 2026-06-30
**Status:** APPROVED

---

## Samenvatting

`update_user_status()` in `profile_router.py` riep `audit_service.log_action()` aan
zonder `best_effort` wrapper. Een falende audit log kon het primaire request blokkeren
(HTTPException of onverwerkte exception propagatie). ADR-019 vereist non-blocking audit logs.

**Fix:** `async with best_effort("user.status_changed audit log"):` wrapper toegevoegd.

---

## Scopebevinding (explore-fase)

De oorspronkelijke planscope (18 call-sites in 8 bestanden) bleek na codebase-analyse 1 ongewrapped
call-site te zijn. De overige 12 call-sites waren reeds correct gewrapped:

| Bestand | Status VOOR Dag 2 |
|---------|-------------------|
| `profile_router.py` (user_management) | ❌ ONGEWRAPPED -- gefixed |
| `crud_router.py` (user_management) | ✅ al gewrapped (4/4) |
| `tenants_list_router.py` | ✅ al gewrapped + session=service.db |
| `tenants_detail_router.py` | ✅ al gewrapped + session=service.db (2/2) |
| `upload_router.py` (documents) | ✅ al gewrapped (db_session=db) |
| `crud_router.py` (documents) | ✅ al gewrapped (db_session=db, 2/2) |
| `processing_router.py` | ✅ al gewrapped (db_session=db) |
| `notifications/router.py` | ✅ al gewrapped (db_session=db, 2/2) |
| `tenant_management/crud_router.py` | ✅ al gewrapped (4/4) |

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/user_management/profile_router.py` | Import `best_effort` + wrapper om `log_action()` |
| `tests/unit/api/v1/user_management/test_profile_router_audit.py` | Nieuw (rode test, aparte commit 0d6801ee) |

---

## Patroon

```python
async with best_effort("user.status_changed audit log"):
    await audit_service.log_action(
        tenant_id=user.tenant_id,
        action="user.status_changed",
        resource=f"user:{user.id}",
        user_id=admin_user.id,
        details={"changes": {"is_active": {"old": old_status, "new": status_update.is_active}}},
    )
```

Conform het patroon in `crud_router.py` (user_management, 4 call-sites, reeds correct).

---

## Tests

| Test | Type | Wat het test |
|------|------|--------------|
| `test_update_user_status_audit_wrapped_in_best_effort` | arch/inspect | `best_effort` aanwezig in functie-body |

Rode test commit: `0d6801ee` (bewijs: ROOD voor fix-commit).
Fix commit: volgende commit.

---

## Niet in scope (gedocumenteerd)

`session=db` ontbreekt bij de meeste `log_action()` aanroepen -- auditlog wordt stil
overgeslagen als `log_action()` geen actieve sessie heeft. Aparte backlog: TODO(SP-AUDIT-004).


## Trainingssamenvatting

- Actor: Een geauthenticeerde beheerder (admin) die de status van een gebruiker wil wijzigen.
- Voorwaarde: De caller heeft een geldig JWT met admin-rechten; de target user bestaat in de database.
- Actie (request): Stuur een `PATCH /users/{user_id}/status` request met body `{"is_active": <bool>}` (`UserStatusUpdate`).
- Systeemverwerking: `require_admin` valideert de admin-rechten. Met `TenantFilterBypass()` wordt de user opgezocht op `user_id`. De huidige `is_active` waarde wordt bewaard, de nieuwe waarde gezet, en `db.commit()` + `db.refresh()` uitgevoerd. Vervolgens wordt binnen `async with best_effort("user.status_changed audit log", db_session=db)` de audit actie `user.status_changed` gelogd via `audit_service.log_action(..., session=db)`.
- Succesrespons: HTTP 200 OK met `UserResponseSchema` inclusief de bijgewerkte `is_active`, tenant naam en rollen.
- Foutrespons: HTTP 401 als de caller geen admin is; HTTP 404 als `user_id` niet bestaat; HTTP 422 bij ongeldige body. Een falende audit log wordt door `best_effort` geabsorbeerd en verandert de HTTP status niet.
- Uitzonderingen: `TenantFilterBypass()` wordt gebruikt om de user op te halen buiten de standaard tenant-filter; de meeste andere `log_action()` call-sites missen nog een expliciete `session=db` parameter (aparte backlog TODO(SP-AUDIT-004)).
