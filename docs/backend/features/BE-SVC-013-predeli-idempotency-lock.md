# BE-SVC-013 -- Council Pre-Deliberation Idempotency Lock (SP-WE-06)

**ID:** BE-SVC-013
**Sprint:** SP-WE-06
**Datum:** 2026-06-01
**ADR:** ADR-027 (WE-003)

---

## Samenvatting

Twee gelijktijdige identieke requests konden twee parallelle Council-deliberations
triggeren voor dezelfde input (WE-003). Dit is verholpen via een Redis SET NX lock
VOOR `council.deliberate()` in `CopilotService.handle_turn()`.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/service.py` | `DeliberationInProgressError` domain exception; `redis: Any | None` constructor parameter; pre-deliberation SET NX lock + `finally` delete in `handle_turn()` |
| `src/core/copilot/api/turn_endpoint.py` | `DeliberationInProgressError` gevangen -> HTTP 429 + `Retry-After: 5` |
| `src/core/copilot/dependencies.py` | `redis=redis` doorgegeven aan `CopilotService` |

## Lock patroon

- **Key:** `copilot:deliberation:{tenant_id}:{sha256(tenant_id:user_id:message)[:16]}`
- **TTL:** 30 seconden (deliberation SLA + marge)
- **Graceful degradation:** `redis=None` -> geen lock, geen crash
- **Vrijgave:** `finally` blok garandeert delete bij success en exception

## Architectuurbeslissingen

1. `DeliberationInProgressError` is een domein-exception (niet `HTTPException`) om de service-laag ontkoppeld te houden van FastAPI. De endpoint vertaalt naar HTTP 429.
2. `redis: Any | None` in constructor vermijdt een hard `from redis.asyncio import Redis` import op module-niveau (minder startup cost).
3. `except DeliberationInProgressError: raise` in de inner try/except laat de exception door zodat `finally` de lock vrijgeeft.

## Trainingssamenvatting

### Flow 1: Pre-deliberation lock voorkomt dubbele deliberation

- **Actor:** CopilotService.handle_turn() (systeem)
- **Voorwaarde:** Twee gelijktijdige identieke requests arriveren voor dezelfde tenant+user+message
- **Actie:** Eerste request acquireert Redis SET NX lock; tweede request probeert SET NX
- **Systeemreactie:** Eerste lock succesvol -> deliberation start; tweede mislukt -> `DeliberationInProgressError`
- **Succesrespons:** Eerste request verloopt normaal; lock vrijgegeven in finally na deliberation
- **Foutrespons:** Tweede request ontvangt HTTP 429 + `Retry-After: 5` header
- **Uitzonderingen:** Redis down (`redis=None`) -> lock overgeslagen; deliberation loopt door zonder bescherming (graceful degradation)

### Flow 2: Lock vrijgave bij deliberation-fout

- **Actor:** CopilotService.handle_turn() (systeem)
- **Voorwaarde:** Lock verkregen; `council.deliberate()` gooit een exception
- **Actie:** `except Exception` vangt de fout; `_blocked_response()` wordt retourneerd
- **Systeemreactie:** `finally` blok draait altijd; `redis.delete(lock_key)` vrijgeeft de lock
- **Succesrespons:** Volgende identieke request kan opnieuw een lock acquireren
- **Foutrespons:** Zonder `finally` zou de lock 30 seconden geblokkeerd blijven
- **Uitzonderingen:** `DeliberationInProgressError` wordt via `except DeliberationInProgressError: raise` doorgegeven zodat finally altijd draait
