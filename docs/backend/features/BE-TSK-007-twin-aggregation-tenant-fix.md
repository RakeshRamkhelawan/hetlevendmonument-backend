# BE-TSK-007: Twin Profile Aggregation Tenant Isolation Fix (B-012)

## Build Summary

Fixed B-012: `src/core/jobs/twin_profile_aggregation_job.py` emetteerde metric `record_twin_aggregation_users_processed(tenant_id=0, ...)` met een hardcoded `tenant_id=0`. Dit vervuild tenant-0 metrics en maakte per-tenant monitoring onmogelijk. Nu worden metrics per tenant bijgehouden en correct geëmitteerd.

## Backend Inventory

| Artefact | Type | Locatie | Wijziging |
|----------|------|---------|-----------|
| `aggregate_all_profiles` | Service functie | `src/core/jobs/twin_profile_aggregation_job.py` | Per-tenant metric tracking |

## Functionele specificatie

### aggregate_all_profiles
- **Input:** `db` (AsyncSession), optioneel `batch_size` (default 500)
- **Werking:** Haalt batches `(tenant_id, human_user_id)` op, roept per entry `ProfileAggregator.aggregate()` aan, houdt per tenant een `tenant_processed_counts` dict bij
- **Metrics:** Alleen succesvolle profielen (profile is truthy) worden geteld; skipped users worden overgeslagen
- **Output:** Stats dict met total, processed, skipped

## Technische specificatie

### Metric emissie
```python
tenant_processed_counts: dict[int, int] = {}
# ... inside loop ...
if profile:
    stats["processed"] += 1
    tenant_processed_counts[tenant_id] = tenant_processed_counts.get(tenant_id, 0) + 1
else:
    stats["skipped"] += 1
# ... after loop ...
for tid, count in tenant_processed_counts.items():
    record_twin_aggregation_users_processed(tid, count)
```

- Geen hardcoded `tenant_id=0` meer
- Skipped users (profile=None) worden niet geteld in metrics

## Acceptatiecriteria

- [x] `record_twin_aggregation_users_processed` wordt nooit aangeroepen met `tenant_id=0`
- [x] Metrics worden per tenant correct geëmitteerd
- [x] Source inspectie bevestigt geen hardcoded literal
- [x] Unit tests slagen

## Open aannames

- Skipped users zijn correct gedetecteerd (profile is None); dit gedrag blijft ongewijzigd

## Trainingssamenvatting

### Flow 1: Dramatiq actor uitvoering

- Actor: APScheduler of directe Dramatiq-aanroep
- Voorwaarde: Actor is geregistreerd op de Redis-broker; cron-trigger is afgegaan
- Actie: Actor wordt uitgevoerd door een Dramatiq-worker
- Systeemverwerking: Actor voert de taak asynchroon uit met correcte tenant-filtering via TenantFilterBypass
- Succesrespons: Taak voltooid zonder exceptions; resultaat gelogd
- Foutrespons: Bij exception: Dramatiq retry-mechanisme actief (max MAX_RETRIES pogingen)
- Uitzonderingen: Als Redis niet beschikbaar is: actor niet uitgevoerd; alert via monitoring
