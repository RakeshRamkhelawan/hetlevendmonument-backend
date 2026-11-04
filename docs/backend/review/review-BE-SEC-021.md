# Review BE-SEC-021 -- Redis-backed rate limiter CVA chat

- Sprint: SP-CVA-P1 Dag 2
- Datum: 2026-06-22
- Reviewer: quality-reviewer (interne review)
- Uitkomst: **APPROVED WITH MINOR GAPS**

## Samenvatting

Redis-backed `cva_chat_limit` correct geimplementeerd in `governance/rate_limiter.py`.
DSM fan-out=0 invariant van `shared` bewaard. Double-checked locking correct.

## Bevindingen

| ID | Ernst | Bevinding | Actie |
|---|---|---|---|
| R1 | MINOR | `copilot_turn_limit` (shared) is nog InMemory-only | Backlog TODO(SP-SEC-RL-001) gedocumenteerd + architecture test aangemaakt |
| R2 | MINOR | SEC-001 X-User-ID header trust in `_get_user_id_from_request` | Backlog architecture test aangemaakt |
| R3 | MINOR | SEC-002 tenant_id ontbreekt in default privacy_rate_limit key | Backlog architecture test aangemaakt |

## CRITICAL/HIGH bevindingen

Geen.

## Verificatie

- pyright: 0 errors
- 7 gerichte tests GROEN
- Copilot turn limit tests: geen timeout meer (0.02s)
