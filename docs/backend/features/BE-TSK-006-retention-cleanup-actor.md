# BE-TSK-006: Retention Cleanup Actor Verification (B-011)

## Build Summary

B-011 gemarkeerd als "already exists" — de `run_retention_cleanup` Dramatiq actor was al aanwezig in `src/workers/actors.py:252`. Geen code-wijzigingen nodig; actor doorloopt verificatie als onderdeel van dit sprint.

## Backend Inventory

| Artefact | Type | Locatie | Wijziging |
|----------|------|---------|-----------|
| `run_retention_cleanup` | Dramatiq actor | `src/workers/actors.py` | Bestaand, geverifieerd |

## Functionele specificatie

### Actor: run_retention_cleanup
- **Trigger:** Gepland dagelijks om 03:00 UTC
- **Werking:** Verwijdert council decisions ouder dan 395 dagen (incl. cascade naar `officer_verdicts`)
- **Output:** Dict met status en timestamp
- **Foutpad:** Exception triggert Dramatiq retry

## Technische specificatie

```python
@dramatiq.actor(
    queue_name="maintenance",
    max_retries=MAX_RETRIES,
    time_limit=600_000,
)
async def run_retention_cleanup() -> dict[str, Any]
```

- Roep interne cleanup functie aan die overblijvende records wist
- `TenantFilterBypass` voor cross-tenant operaties

## Acceptatiecriteria

- [x] Actor is geregistreerd in `actors.py`
- [x] Actor heeft `.send()` methode
- [x] Actor is geen `_DummySender`
- [x] Unit test `test_retention_cleanup_actor_exists` slaagt

## Open aannames

- Retentieperiode 395 dagen is hardcoded; configurabel maken in toekomstige sprint

## Trainingssamenvatting

### Flow 1: Dramatiq actor uitvoering

- Actor: APScheduler of directe Dramatiq-aanroep
- Voorwaarde: Actor is geregistreerd op de Redis-broker; cron-trigger is afgegaan
- Actie: Actor wordt uitgevoerd door een Dramatiq-worker
- Systeemverwerking: Actor voert de taak asynchroon uit met correcte tenant-filtering via TenantFilterBypass
- Succesrespons: Taak voltooid zonder exceptions; resultaat gelogd
- Foutrespons: Bij exception: Dramatiq retry-mechanisme actief (max MAX_RETRIES pogingen)
- Uitzonderingen: Als Redis niet beschikbaar is: actor niet uitgevoerd; alert via monitoring
