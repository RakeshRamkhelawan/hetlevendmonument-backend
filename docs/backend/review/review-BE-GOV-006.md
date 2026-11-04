# Review BE-GOV-006: RC-009a Agent execute rate limits

**Reviewer:** code-reviewer (SP-GOV-002 dag 2)
**Datum:** 2026-06-23
**Verdict:** APPROVED

## Bevindingen

Geen CRITICAL of HIGH bevindingen.

### PASS: Rate limit juist
10/min per tenant+user via Redis-backed sliding window met InMemory fallback.
Consistent met patroon van `cva_chat_limit` / `copilot_turn_limit` in hetzelfde bestand.

### PASS: ADR-033 compliant
`check_agent_execute_limit` wordt aangeroepen vanuit `agent_execute_limit_dep` in
`agents/dependencies.py` (facade, own-domain, exempt). Geen directe governance-import
in router files.

### PASS: DoS-bescherming
Alle 4 muterende agent-endpoints (execute dispatcher, execute primary, execute legacy,
collaborate) zijn gedekt. Read-only endpoints (/stats, /health, /catalog) zijn niet
beperkt (juist: hogere leeslimieten per ADR-033 backend-patronen).

### PASS: Redis fallback aanwezig
`_get_redis_limiter()` met double-checked locking. Bij Redis-fout: InMemory fallback.
Consistent met bestaand patroon in `cva_chat_limit`.

### PASS: Retry-After header aanwezig
`headers={"Retry-After": str(_AGENT_EXECUTE_WINDOW)}` in beide 429-raises.
