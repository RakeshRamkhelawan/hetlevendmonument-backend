# BE-GOV-006: RC-009a -- Agent execute/collaborate rate limits (10/min)

**Sprint:** SP-GOV-002 Dag 2
**Datum:** 2026-06-23
**Status:** APPROVED

## Omschrijving

De agent execute en collaborate endpoints hadden geen rate limiting (RC-009a bevinding,
DoS-risico). Na deze fix worden alle 4 endpoints (POST /execute dispatcher, POST
/agent/execute/{id}, POST /execute/{id} legacy, POST /collaborate) beperkt tot
10 requests per minuut per tenant+user.

## Wijzigingen

### `src/core/governance/rate_limiter.py`
- `_AGENT_EXECUTE_MAX = 10`, `_AGENT_EXECUTE_WINDOW = 60` constanten toegevoegd.
- `check_agent_execute_limit(tenant_id, user_id)` toegevoegd: async functie die
  Redis-backed check doet (sliding window) met InMemory fallback.
  Raises `HTTPException(429)` bij overschrijding.
- `agent_execute_limit(func)` decorator toegevoegd: zoekt `Request` via isinstance,
  haalt tenant_id/user_id uit `request.state`, roept `check_agent_execute_limit` aan.

### `src/core/api/v1/agents/dependencies.py`
- `from fastapi import Depends, Request` (Request toegevoegd).
- `agent_execute_limit_dep(http_request, current_user)` toegevoegd: FastAPI Depends
  functie die `check_agent_execute_limit(current_user.tenant_id, current_user.id)` aanroept
  via lazy import van `rate_limiter`.
- `agent_execute_limit_dep` en `Request` toegevoegd aan `__all__`.

### `src/core/api/v1/agents/agent_execution_router.py`
- `agent_execute_limit_dep` geimporteerd vanuit `dependencies`.
- `_rl: None = Depends(agent_execute_limit_dep)` toegevoegd aan 3 handlers:
  `execute_agent_dispatcher`, `execute_agent_primary`, `execute_agent_legacy`.

### `src/core/api/v1/agents/agent_management_router.py`
- `agent_execute_limit_dep` geimporteerd vanuit `dependencies`.
- `_rl: None = Depends(agent_execute_limit_dep)` toegevoegd aan `collaborate_agents_route`.

## Tests
- `tests/unit/api/v1/agents/test_agent_execute_rate_limit.py` -- 3 tests GROEN:
  - `test_execute_router_has_rate_limit` (arch scan: "agent_execute_limit" in execution_router)
  - `test_management_router_has_rate_limit` (arch scan: "agent_execute_limit" in management_router)
  - `test_rate_limiter_exports_agent_execute_limit` (arch scan: "agent_execute_limit" in rate_limiter)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-GOV-002 Dag 2 RC-009a: agent execute/collaborate rate limits (10/min, Redis-backed). check_agent_execute_limit + agent_execute_limit in rate_limiter. agent_execute_limit_dep Depends facade in agents/dependencies.py. \_rl param in 4 handlers. 3 tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-GOV-002 Dag 2 RC-009a: agent execute/collaborate rate limits (10/min, Redis-backed). check_agent_execute_limit + agent_execute_limit in rate_limiter. agent_execute_limit_dep Depends facade in agents/dependencies.py. \_rl param in 4 handlers. 3 tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
