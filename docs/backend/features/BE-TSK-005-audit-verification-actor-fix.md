# BE-TSK-005: Audit Verification Dramatiq Actor Fix (B-010)

## Build Summary

Fixed B-010: `src/core/jobs/audit_verification.py` contained a working `AuditTrailVerificationJob` class but had no Dramatiq actor wrapper in `src/workers/actors.py`, meaning the hash chain verification job never ran in production. Also fixed a critical pre-existing bug where `store_result()` attempted to `session.add()` an unmapped plain Python class (`AuditVerificationResult`), which would crash at runtime.

## Backend Inventory

| Artefact | Type | Locatie | Wijziging |
|----------|------|---------|-----------|
| `run_audit_verification` | Dramatiq actor | `src/workers/actors.py` | Nieuw |
| `AuditTrailVerificationJob.store_result()` | Service-methode | `src/core/jobs/audit_verification.py` | Bugfix: verwijderd ongeldige `session.add()` |

## Functionele specificatie

### Actor: run_audit_verification
- **Trigger:** Gepland dagelijks om 03:00 UTC via Dramatiq scheduler
- **Werking:** Enumereert alle actieve tenants, verifieert per tenant de audit log hash chain integriteit via `HashChainVerifier`, update `Tenant.last_verified_at`
- **Output:** Dict met total_tenants, verified_tenants, failed_tenants, total_broken_chains, duration_ms
- **Foutpad:** Per-tenant failures worden gelogd maar stoppen de job niet; actor-level exception triggert Dramatiq retry

## Technische specificatie

### run_audit_verification
```python
@dramatiq.actor(
    queue_name="maintenance",
    max_retries=MAX_RETRIES,
    time_limit=600_000,  # 10 minutes
)
async def run_audit_verification() -> dict[str, Any]
```

- Gebruikt `TenantFilterBypass()` voor cross-tenant tenant-enumeratie in worker-context (geen HTTP request = geen tenant ContextVar)
- Opent `get_db_session()` als async context manager
- Roept `AuditTrailVerificationJob(db_session=session).run()` aan
- Retourneert samenvattingsdict; gooit exception bij onverwachte fouten voor Dramatiq retry

### store_result bugfix
- **Oorspronkelijk:** `self.db_session.add(audit_result)` waar `audit_result` een ongemapte Python class was -> `UnmappedInstanceError`
- **Fix:** Alleen `Tenant.last_verified_at` updaten en `commit()` aanroepen

## Trainingssamenvatting

| Stap | Beschrijving |
|------|-------------|
| Actor | Systeemscheduler (Dramatiq) |
| Voorwaarde | Actor is geregistreerd, database bereikbaar |
| Actie | `run_audit_verification.send()` |
| Systeemreactie | Enumereert tenants, verifieert hash chains, update timestamps |
| Succesrespons | `{"status": "success", "total_tenants": N, ...}` |
| Foutrespons | Exception -> Dramatiq retry (max_retries=MAX_RETRIES) |
| Uitzonderingen | Per-tenant verificatie-faal wordt gelogd, volgende tenant wordt verwerkt |

## Acceptatiecriteria

- [x] `run_audit_verification` heeft `.send()` methode
- [x] Actor is geen `_DummySender` wanneer dramatiq beschikbaar is
- [x] `store_result()` doet geen `session.add()` van ongemapte class
- [x] `TenantFilterBypass` is aanwezig in actor body
- [x] Unit tests slagen

## Open aannames

- `AuditVerificationResult` class is dead code (nooit een ORM tabel geweest); verwijderen in toekomstige cleanup
