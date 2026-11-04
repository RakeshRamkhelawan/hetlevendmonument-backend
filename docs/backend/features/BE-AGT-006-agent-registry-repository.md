# BE-AGT-006: AgentRegistryRepository + AgentRegistry Migration (SP-AGT-002 Dag 4)

## Status

APPROVED

## Summary

Dag 4 of SP-AGT-002 (ADR-034 boundary enforcement). Eliminates all
`get_async_session` call sites from `src/core/agents/agent_registry.py` and
removes the module-level singleton. A new concrete repository
`AgentRegistryRepository` (in `src/core/database/`) implements the
`IAgentRegistryRepository` protocol and is injected via the constructor.

## Motivation

ADR-034 (agent_runtime boundary, facade pattern) forbids direct
`src.core.database` imports inside `src/core/agents/`. After Dag 3 the DSM
fan-out was 12. Dag 4 target: reduce to 11 by migrating `agent_registry.py`
off the `get_async_session` fallback pattern.

## Changes

| File | Change |
|------|--------|
| `src/core/database/agent_registry_repository.py` | New -- concrete `AgentRegistryRepository` (6 methods, full tenant isolation) |
| `src/core/shared/interfaces.py` | Added `update_agent` + `delete_agent` to `IAgentRegistryRepository` |
| `src/core/agents/agent_registry.py` | Removed `get_async_session` import; added `repository` parameter; replaced 3 DB blocks with `if self._repository / elif self._db_session / else raise` pattern; removed module-level singleton |
| `src/core/api/agent_endpoints.py` | `get_agent_registry_dependency` now creates `AgentRegistry(repository=AgentRegistryRepository(session))` |
| `src/core/api/v1/cva/public_router.py` | Same DI factory update |
| `src/core/api/v1/agentic/agent_discovery.py` | Removed `get_agent_registry` singleton call; all 6 endpoints now inject `db: AsyncSession = Depends(get_db)` and create registry via repository |
| `tests/unit/agents/test_agent_registry_repository.py` | New -- 8 tests (protocol + isolation guards) |
| `tests/unit/test_agent_registry_coverage.py` | Updated 6 tests from `@patch(get_async_session)` to mock repository injection; removed dead `TestSingletonFunction` class |
| `tests/unit/test_agent_endpoints.py` | Updated assertion in `test_get_agent_registry_dependency` |

## Repository Design

`AgentRegistryRepository` satisfies ADR-005 (tenant_id NOT NULL) and ADR-011
(session injected, caller owns transaction, repository only `flush()`):

- `get_registered_agent_by_agent_id(agent_id, tenant_id)` -- always filters by tenant_id
- `get_registered_agents(tenant_id, limit, offset)` -- paginated, tenant-scoped
- `get_active_agents(tenant_id, limit, offset)` -- heartbeat threshold + isnot(None) guard
- `register_agent(registration)` -- add + flush, no commit
- `update_agent(agent_id, tenant_id, values)` -- UPDATE + flush, no commit
- `delete_agent(agent_id, tenant_id)` -- DELETE + flush, no commit

## Test Results

- 8 new tests: 8/8 PASS
- Architecture + unit/api regressiecheck: 475/475 PASS
- Full unit suite: 12699 passed, 0 failed, 236 skipped, 20 xfailed

## ADR Compliance

- ADR-034: `src.core.agents.agent_registry` no longer imports `get_async_session` from `src.core.database.database`. DSM fan-out reduced 12 -> 11.
- ADR-005: All repository methods include `WHERE tenant_id = ?`
- ADR-011: Repository only flushes; callers own the transaction

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
