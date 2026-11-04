---
id: BE-AGT-007
title: AgentDiscoveryService Migration -- AsyncSessionFactory injection (SP-AGT-002 Dag 5)
sprint: SP-AGT-002 Dag 5
status: APPROVED
date: 2026-06-10
---

# BE-AGT-007: AgentDiscoveryService Migration

## Samenvatting

`AgentDiscoveryService` importeerde `get_async_session` direct vanuit
`src.core.database.database` (ADR-034 grensovertreding). DSM fan-out was 10.
Na deze dag: importverbod verwijderd, `AsyncSessionFactory` injection-patroon ingevoerd,
DSM fan-out = 9.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/agent_discovery.py` | `get_async_session` verwijderd; `_db_session / _async_session_factory` in `__init__`; `_session_scope` via `getattr` |
| `src/core/agents/agent_router_agent.py` | `async_session_factory` parameter toegevoegd aan `__init__` + `get_agent_router()` |
| `src/core/shared/interfaces.py` | `AsyncSessionFactory` type alias aangemaakt + in `__all__` opgenomen |
| `src/core/api/v1/cva/public_router.py` | `execute_managed_cva_agent`: directe `db.execute(select(RegisteredAgent)...)` vervangen door `AgentRegistryRepository`; `fallback_caps` bug (CR-005) gefixed |
| `tests/unit/agents/test_agent_discovery_service.py` | 6 tests aangemaakt (3 RED voor fix, 3 pre-existing GREEN) |
| `tests/unit/test_agent_discovery_find_by_functions.py` | Patches op `get_async_session` vervangen door `_make_service_with_ctx()` factory-injection |
| `tests/unit/test_agent_router_agent.py` | Lambda `__init__` mocks bijgewerkt met `async_session_factory=None` parameter |

## Trainingssamenvatting

**Actor:** `AgentDiscoveryService`

**Voorwaarden:**
- Opgeroepen vanuit `AgentRouterAgent.initialize()` of direct via tests
- Kan worden geconstrueerd via `__init__` (normaal pad) of `__new__` (test-pad)
- Heeft ofwel een geinjected `db_session` of `async_session_factory` nodig

**Actie:** DB-query via `_session_scope` context manager

**Systeemreactie:**
- Als `_db_session` aanwezig: yield de sessie direct
- Als `_async_session_factory` aanwezig: open context via factory en yield
- Als geen van beide: `RuntimeError` (gevangen door `except Exception` in publieke methoden -> leeg resultaat)

**Succes:** Query uitgevoerd, agenten teruggegeven

**Fout:** Geen sessie/factory ingesteld -> lege lijst teruggegeven (degraded mode)

**Uitzonderingen:** `__new__`-geconstrueerde objecten in tests missen `_db_session` en
`_async_session_factory` attributen; `getattr(..., None)` zorgt voor veilige fallback

## ADR-naleving

| ADR | Naleving |
|-----|----------|
| ADR-034 | PASS -- `get_async_session` import verwijderd uit agents/ |
| ADR-011 | PASS -- repository-patroon in `public_router.py` gebruikt |
| ADR-005 | PASS -- alle repository-aanroepen filteren op `tenant_id` |

## DSM fan-out

| Meting | Waarde |
|--------|--------|
| Voor Dag 5 | 10 |
| Na Dag 5 | 9 |
| Sprint target | 9 (BEHAALD) |
