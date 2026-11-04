# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-021
- Feature naam: Redis-backed rate limiter voor CVA chat endpoints (SEC-001/005)
- Status: APPROVED
- Auteur: SP-CVA-P1 Dag 2
- Reviewer: zie docs/backend/review/review-BE-SEC-021.md
- Datum: 2026-06-22
- Gerelateerde user story / ticket: AGENT-CVA-COUNCIL-AUDIT-2026-06-20 SEC-001 + SEC-005
- Gerelateerde router / module: src/core/governance/rate_limiter.py, src/core/shared/rate_limiter.py
- Gerelateerde database tabellen: nvt (Redis)
- Versie: 1.0

---

## Doel en scope

### Doel

Multi-worker rate-limit bypass voorkomen: `cva_chat_limit` gebruikte `InMemoryRateLimiter` die
per Gunicorn-worker draait. Met N workers was de effectieve limiet N*30 req/min. Door over te
stappen op `RedisRateLimiter` (sliding window Lua-script, atomisch) wordt de limiet cross-worker
gedeeld.

### In scope

- `cva_chat_limit` in `governance/rate_limiter.py` omgebouwd naar Redis-backed met InMemory fallback
- `_get_redis_limiter()` lazy-init met asyncio.Lock double-checked locking in governance
- Reconnect-reset: Redis-limiter op None zetten bij runtime Redis-failure
- `shared/rate_limiter.py` blijft pure InMemory (DSM fan-out=0 invariant bewaard)

### Out of scope

- `copilot_turn_limit` (importeert uit shared, DSM constraint -- backlog TODO(SP-SEC-RL-001))
- SEC-001 X-User-ID header spoofing (backlog SEC-001 architecture test toegevoegd)
- SEC-002 tenant_id ontbreekt in default key (backlog SEC-002 architecture test toegevoegd)

---

## Build summary

- Nieuw gebouwd: `_get_redis_limiter()`, `_redis_rate_limiter`, `_redis_limiter_lock` in governance
- Gewijzigd: `cva_chat_limit` in governance -- volledig Redis+InMemory wrapper; `reset_snapshot_rate_limits` reset ook governance Redis state
- Verwijderd: Redis-code uit `shared/rate_limiter.py` (DSM constraint)
- Beinvloede bestaande flows: CVA chat endpoints (30 req/min, nu cross-worker)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
|---|---|---|---|---|
| 1 | _get_redis_limiter | async function | src/core/governance/rate_limiter.py | Nieuw |
| 2 | cva_chat_limit | decorator | src/core/governance/rate_limiter.py | Wijziging |
| 3 | reset_snapshot_rate_limits | function | src/core/governance/rate_limiter.py | Wijziging |
| 4 | shared/rate_limiter.py | module | src/core/shared/rate_limiter.py | Wijziging (Redis verwijderd) |

---

## Technische details

### Redis-init patroon (governance/rate_limiter.py)

- Lazy init: eerste CVA chat request probeert Redis verbinding
- Double-checked locking via `asyncio.Lock` om race bij concurrent cold-start te voorkomen
- Fallback: `except Exception` → log warning + return None → InMemory path in `cva_chat_limit`
- Redis-failure tijdens request: `_redis_rate_limiter = None` zodat volgende request opnieuw probeert

### DSM architectuur

- `shared` module houdt fan-out=0 (geen cross-module imports)
- `governance` mag importeren uit `database` en `security` lagen
- Redis-init leeft in governance, shared blijft onafhankelijk

### Tests

- `tests/unit/governance/test_redis_rate_limiter_wiring.py`: 3 tests GROEN
- `tests/architecture/test_rate_limiter_sec_backlog.py`: 2 tests ROOD (backlog SEC-001+SEC-002)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-CVA-P1 Dag 2: Redis-backed cva_chat_limit (SEC-001/005). \_get_redis_limiter() lazy-init + asyncio.Lock double-checked locking in governance. InMemory fallback. DSM fan-out=0 shared bewaard. Backlog architecture tests SEC-001+SEC-002. 7 gerichte tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-CVA-P1 Dag 2: Redis-backed cva_chat_limit (SEC-001/005). \_get_redis_limiter() lazy-init + asyncio.Lock double-checked locking in governance. InMemory fallback. DSM fan-out=0 shared bewaard. Backlog architecture tests SEC-001+SEC-002. 7 gerichte tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
