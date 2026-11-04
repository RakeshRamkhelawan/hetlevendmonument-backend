# BE-TSK-008: Pack Health Cross-Tenant Scan Fix (B-014)

## Build Summary

Fixed B-014: `src/core/jobs/pack_health_job.py` voerde pack health aggregation uit zonder tenant filter, wat in multi-tenant context leidde tot cross-tenant data zichtbaarheid. Ook vervangen: `datetime.utcnow()` -> `datetime.now(timezone.utc)` (meerdere locaties) om timezone-aware deprecation warnings te voorkomen.

## Backend Inventory

| Artefact | Type | Locatie | Wijziging |
|----------|------|---------|-----------|
| `aggregate_pack_usage` | Service functie | `src/core/jobs/pack_health_job.py` | `tenant_id` parameter toegevoegd |
| `calculate_pack_health` | Service functie | `src/core/jobs/pack_health_job.py` | `tenant_id` parameter toegevoegd |
| `update_pack_usage_counts` | Service functie | `src/core/jobs/pack_health_job.py` | `tenant_id` parameter doorgegeven |
| `update_pack_metrics` | Entry point | `src/core/jobs/pack_health_job.py` | `tenant_id` parameter toegevoegd |
| `run_pack_health_aggregation` | Dramatiq actor | `src/workers/actors.py` | `TenantFilterBypass` toegevoegd |
| `run_daily_maintenance` | Dramatiq actor | `src/workers/actors.py` | `TenantFilterBypass` toegevoegd |

## Functionele specificatie

### update_pack_metrics(tenant_id=None)
- **Input:** Optioneel `tenant_id` (int | None)
- **Werking:** Wanneer `tenant_id` is gezet, filteren alle interne queries (`aggregate_pack_usage`, `calculate_pack_health`, pack lookup) op die tenant
- **Backward compat:** `None` = bestaand gedrag (alle tenants) voor compatibiliteit

## Technische specificatie

### Tenant filtering per functie
```python
async def aggregate_pack_usage(db, since, tenant_id=None):
    stmt = select(PackActivationAuditLog)
    if tenant_id is not None:
        stmt = stmt.where(PackActivationAuditLog.tenant_id == tenant_id)
    ...

async def calculate_pack_health(db, tenant_id=None):
    stmt = select(DomainPack)
    if tenant_id is not None:
        stmt = stmt.where(DomainPack.tenant_id == tenant_id)
    ...
```

### Actor wijzigingen
- `run_pack_health_aggregation` en `run_daily_maintenance` wrappen `update_pack_metrics()` met `TenantFilterBypass()`
- `datetime.utcnow()` vervangen door `datetime.now(timezone.utc)` in `pack_health_job.py` en `actors.py`

## Acceptatiecriteria

- [x] `calculate_pack_health` filtert op `DomainPack.tenant_id` wanneer `tenant_id` is meegegeven
- [x] `aggregate_pack_usage` filtert op `PackActivationAuditLog.tenant_id`
- [x] `update_pack_usage_counts` doorgeeft tenant filter naar subfuncties
- [x] `TenantFilterBypass` is aanwezig in actor body
- [x] Geen `datetime.utcnow()` meer in gewijzigde bestanden
- [x] Unit tests slagen

## Open aannames

- Actors gebruiken `TenantFilterBypass` omdat ze in worker-context draaien zonder HTTP request tenant ContextVar

## Trainingssamenvatting

### Flow 1: Dramatiq actor uitvoering

- Actor: APScheduler of directe Dramatiq-aanroep
- Voorwaarde: Actor is geregistreerd op de Redis-broker; cron-trigger is afgegaan
- Actie: Actor wordt uitgevoerd door een Dramatiq-worker
- Systeemverwerking: Actor voert de taak asynchroon uit met correcte tenant-filtering via TenantFilterBypass
- Succesrespons: Taak voltooid zonder exceptions; resultaat gelogd
- Foutrespons: Bij exception: Dramatiq retry-mechanisme actief (max MAX_RETRIES pogingen)
- Uitzonderingen: Als Redis niet beschikbaar is: actor niet uitgevoerd; alert via monitoring
