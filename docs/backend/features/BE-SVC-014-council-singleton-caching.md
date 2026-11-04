# BE-SVC-014 -- AgentCouncil Singleton/Caching (SP-WE-08)

**ID:** BE-SVC-014
**Sprint:** SP-WE-08
**Datum:** 2026-06-01
**ADR:** ADR-027 (WE-009)

---

## Samenvatting

`build_council(db)` maakte per FastAPI-request volledig nieuwe instanties van alle 8 officers
(WE-009). Stateless officers (geen request-specifieke state) worden nu als module-level
singletons gecached via `@lru_cache`. `InMemoryRateLimiter` wordt als persistent
module-level singleton gehouden zodat rate-limiting state overleeft tussen requests.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/council/factory.py` | `from functools import lru_cache`; 4 `@lru_cache(maxsize=1)` functies: `_get_ethics_officer()`, `_get_sanity_officer()`, `_get_compliance_officer()`, `_get_security_officer()`; `_PERSISTENT_RATE_LIMITER` module-level singleton; `build_council()` gebruikt singletons voor stateless officers |

## Officer-classificatie

| Officer | Type | Reden |
| --- | --- | --- |
| EthicsOfficer | Stateless singleton | Lexicon frozensets, geen request state |
| SanityOfficer | Stateless singleton | Pattern matching, geen request state |
| ComplianceOfficer | Stateless singleton | Policy rules, adapters stateless |
| SecurityOfficer | Stateless singleton | PromptGuard/RBACService stateless |
| PrivacyOfficer | Per-request | DB-session consent gate, twin_service |
| RiskOfficer | Per-request | tenant_id uit ContextVar, DB risk register |
| AuditOfficer | Per-request | DB-session audit writer |
| ResourceOfficer | Per-request (persistent rate limiter) | DB prefs_repo; rate limiter nu persistent |

## Thread/asyncio veiligheid

- `lru_cache` is thread-safe in CPython (GIL)
- `InMemoryRateLimiter._cleanup_old_entries()` is sync (geen `await`) -> atomisch in asyncio event loop
- State kruist geen Gunicorn-workers (in-memory, by design)

## Trainingssamenvatting

### Flow 1: Council instantiatie met singleton officers

- **Actor:** `build_council(db)` (systeem, per FastAPI request)
- **Voorwaarde:** Eerste request na app startup
- **Actie:** `build_council(db)` aangeroepen
- **Systeemreactie:** Stateless officers (Compliance/Security/Ethics/Sanity) teruggelezen uit `lru_cache`; stateful officers (Privacy/Risk/Audit/Resource) nieuw aangemaakt
- **Succesrespons:** AgentCouncil klaar; ~4 officer constructors bespaard per request
- **Foutrespons:** n/a (lru_cache faalt niet)
- **Uitzonderingen:** Na code-deploy: `lru_cache` gecleared door process restart; eerste request maakt nieuwe singletons aan

### Flow 2: Rate limiting persistent over requests

- **Actor:** ResourceOfficer (council lid)
- **Voorwaarde:** Tweede request van dezelfde tenant binnen rate-limit window
- **Actie:** `_PERSISTENT_RATE_LIMITER.check(tenant_id, ...)` aangeroepen
- **Systeemreactie:** `InMemoryRateLimiter._requests[tenant_id]` bevat ook counts van vorige requests
- **Succesrespons:** Rate limit correct afgedwongen over requests
- **Foutrespons:** Overschreden limiet -> ResourceOfficer DEFERRED verdict
- **Uitzonderingen:** Worker restart cleart de in-memory state (acceptabel -- P2 issue)
