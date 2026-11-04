# BE-TSK-002: GDPR Purge Dramatiq Actor

> SP-E05: GDPR purge -- echte scheduler
> Status: Implemented | Sprint: SP-E05 | Datum: 2026-05-29

---

## 1. Build Summary

De `_schedule_purge_task` stub in `gdpr_compliance_endpoints.py` is vervangen door een echte Dramatiq actor (`purge_user_data`) die GDPR Art. 17 anonimisering uitvoert. De actor draait op de `maintenance` queue, heeft `max_retries=3`, en anonymiseert (niet hard-delete) user data om de audit trail te behouden.

### Gewijzigde bestanden
- `src/core/actors/gdpr_purge.py` -- nieuw, Dramatiq actor + `_DummySender` fallback
- `src/core/api/gdpr_compliance_endpoints.py` -- `_schedule_purge_task` stub verwijderd, TODO verwijderd
- `tests/unit/test_sp_e05_gdpr_purge.py` -- 12 unit tests

---

## 2. Actor Specificatie

### `purge_user_data(user_id: int, tenant_id: int, scope: str = "all")`

| Attribuut | Waarde |
|-----------|--------|
| Broker | Dramatiq + Redis (ADR-006) |
| Queue | `maintenance` |
| `max_retries` | 3 |
| `time_limit` | 300_000 ms (5 minuten) |
| Idempotent | Ja -- re-running overschrijft `[GDPR PURGED]` met `[GDPR PURGED]` |

### Scope gedrag

| Scope | Actie |
|-------|-------|
| `all` | `messages` + `profile` |
| `messages` | Anonimiseer `conversation_messages.content` en `conversations.title` |
| `profile` | Anonimiseer `User.email`, `hashed_password`, `is_active`, `deleted_at` |

### Anonimisering details

- `conversation_messages.content` -> `'[GDPR PURGED]'`
- `conversations.title` -> `'[GDPR PURGED]'`
- `User.email` -> `f"purged_{user_id}@purged.invalid"`
- `User.hashed_password` -> `'[PURGED]'`
- `User.is_active` -> `False`
- `User.deleted_at` -> `datetime.now(timezone.utc)`

---

## 3. Tenant Isolatie

Alle queries filteren expliciet op `tenant_id` + `user_id`:

```sql
UPDATE conversation_messages
SET content = '[GDPR PURGED]'
WHERE conversation_id IN (
    SELECT id FROM conversations
    WHERE user_id = :user_id AND tenant_id = :tenant_id
)
```

```sql
UPDATE conversations
SET title = '[GDPR PURGED]'
WHERE user_id = :user_id AND tenant_id = :tenant_id
```

```sql
UPDATE users
SET email = ..., hashed_password = ..., is_active = False, deleted_at = ...
WHERE id = :user_id AND tenant_id = :tenant_id
```

Cross-tenant purge is fysiek onmogelijk door de composite WHERE clause.

---

## 4. Audit Logging

De actor schrijft een `best_effort` audit log na succesvolle anonimisering:

- `action`: `gdpr_purge_executed`
- `resource`: `f"user_data:{user_id}"`
- `details`: resultaten dict (rowcounts per categorie)
- `event_type`: `gdpr_purge`
- `threat_level`: `warning`

Als het audit log faalt, wordt een `logger.warning` geemit maar faalt de primaire purge NIET.

---

## 5. Error Handling

| Scenario | Gedrag |
|----------|--------|
| DB connectie fout | Dramatiq retry (max 3x) |
| Query timeout | Dramatiq retry (max 3x) |
| Audit log faalt | `logger.warning`; purge blijft succesvol |
| Actor na 3 retries nog steeds falend | Dead letter queue (Dramatiq default) |

---

## 6. Trainingssamenvatting

| Veld | Inhoud |
| --- | --- |
| **Actor** | GDPR compliance module / Dramatiq worker |
| **Voorwaarde** | DSAR-verzoek geaccepteerd; `user_id` + `tenant_id` beschikbaar |
| **Actie** | `_schedule_purge_task(user_id, tenant_id, scope)` aangeroepen |
| **Systeemreactie** | `purge_user_data.send()` stuurt bericht naar Redis; worker voert anonimisering uit |
| **Succesrespons** | User data geanonimiseerd; audit log bijgewerkt; HTTP 200/202 aan client |
| **Foutrespons** | Actor failure: max_retries=3; na 3x: dead letter queue; client kreeg al 200 |
| **Uitzonderingen** | Scope "all" purgeert berichten + profiel; cross-tenant altijd geblokkeerd door tenant_id filter |

---

## 7. Dependencies

- `dramatiq` (broker: Redis)
- `sqlalchemy` (asyncpg)
- `src.core.database.session.get_db_session`
- `src.core.database.tenant_query_filter.TenantFilterBypass`
- `src.core.models.rbac_models.User`
- `src.core.governance.models.AuditLog`
- `src.core.utils.best_effort`

---

## 8. Testdekking

| Test | Status |
|------|--------|
| `_schedule_purge_task` verstuurt Dramatiq bericht | PASS |
| `purge_user_data` actor bestaat | PASS |
| Geen TODO-comment meer | PASS |
| Actor is Dramatiq-decorated (heeft `.send()`) | PASS |
| `tenant_id` wordt doorgegeven | PASS |
| Geen Celery import | PASS |
| `tenant_id` filter aanwezig | PASS |
| Geen hard DELETE | PASS |
| `max_retries` geconfigureerd | PASS |
| Geen PII in logs | PASS |
| Unauthenticated request -> 401 | PASS |
| Response format correct | PASS |
