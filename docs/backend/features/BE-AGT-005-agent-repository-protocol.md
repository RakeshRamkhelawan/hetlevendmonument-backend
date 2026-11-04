# BE-AGT-005: Agent Repository Protocol Layer (SP-AGT-002 Dag 3)

**Sprint:** SP-AGT-002 -- ADR-034 Agent Runtime Boundary
**Dag:** 3 van 3
**Datum:** 2026-06-10
**Status:** IMPLEMENTED

---

## Samenvatting

Introduceert de repository-protocol laag voor de agents/ module conform ADR-034 en ADR-011.
Verwijdert de directe `src.core.database` import uit `base_agent.py` (was een pre-existing no-op).
Maakt een concrete `AgentRepository` implementatie beschikbaar voor toekomstige migratie van
`agent_registry.py` en `agent_discovery.py`.

---

## Deliverables

| Bestand | Wijziging | Reden |
|---------|-----------|-------|
| `src/core/shared/interfaces.py` | Toegevoegd: `IAgentRepository`, `IAgentRegistryRepository`, `IRedisRepository` | ADR-034 ss2.1: protocols leven in shared/ |
| `src/core/database/agent_repository.py` | Nieuw: concrete `AgentRepository` implementatie | ADR-011 repository pattern |
| `src/core/agents/base_agent.py` | Verwijderd: deferred `db_manager` import L481 (no-op block); fixed 3 pre-existing pyright errors (forward-ref annotation met pipe-operator) | ADR-034 fan-out reductie + pyright 0-errors |
| `tests/unit/agents/test_agent_repository_protocol.py` | Nieuw: 5 protocol-conformance tests | test-first |
| `tests/unit/agents/test_agent_repository_isolation.py` | Nieuw: 1 tenant-isolatie test met WHERE-clause verificatie | ADR-005 isolatietest vereiste |

---

## Protocol Interfaces (src/core/shared/interfaces.py)

### IAgentRepository
```
get_agent_by_id(agent_id: int, tenant_id: int) -> Any | None
get_agents_by_tenant(tenant_id: int, limit: int = 50, offset: int = 0) -> list[Any]
save_agent(agent: Any) -> Any
```

### IAgentRegistryRepository
```
get_registered_agent_by_agent_id(agent_id: str, tenant_id: int) -> Any | None
get_registered_agents(tenant_id: int, limit: int = 50, offset: int = 0) -> list[Any]
get_active_agents(tenant_id: int, limit: int = 50, offset: int = 0) -> list[Any]
register_agent(registration: Any) -> Any
```

### IRedisRepository
```
get(key: str) -> bytes | None
set(key: str, value: str | bytes, ttl: int | None = None) -> None
delete(key: str) -> None
```

---

## Concrete Implementatie (src/core/database/agent_repository.py)

`AgentRepository` implementeert `IAgentRepository` structureel (pyright-verified).
- `get_agent_by_id`: SELECT met `Agent.id == agent_id AND Agent.tenant_id == tenant_id`
- `get_agents_by_tenant`: SELECT met `Agent.tenant_id == tenant_id` + LIMIT/OFFSET
- `save_agent`: session.add() + flush(); caller owns de transactie

---

## base_agent.py wijziging

**Verwijderd:** try-block op L481-511 met deferred `from src.core.database.database import db_manager`.
**Reden:** `audit_service.log_action()` vereist een sessie; zonder sessie (session=None) produceerde
de call al een stille no-op. De reasoning trace data blijft bewaard in `self.reasoning_trace`.

**Pre-existing pyright fixes (bonus):**
- L70: `"LLMClient" | None` -> `LLMClient | None` (forward-ref quotes overbodig met future annotations)
- L93: `"ToolBrokerService" | None` -> `ToolBrokerService | None` (idem)
- L735: `"LLMClient" | None` -> `LLMClient | None` (idem)
Baseline voor base_agent.py was 1; nu 0 (reductie).

---

## DSM Impact

Baseline (dag 2): 13 directe `src.core.database` imports in `src/core/agents/`
Na dag 3: **12** (base_agent.py deferred import verwijderd = -1)

Resterende 12 imports (gepland voor volgende sprints):
- `agent_registry.py`: 1 top-level + 3 deferred = 4 (grootste kandidaat voor dag 4+)
- `agent_discovery.py`: 1 top-level = 1
- `autonomous_agent.py`: 1 (redis) = 1
- `seed_agent_registry.py`: 1 deferred = 1
- `diagnostics_agent/database.py`: 1 (DEPRECATED facade) = 1
- `knowledge_agent/database.py`: 1 (DEPRECATED facade) = 1
- `sentiment_agent/database.py`: 1 (DEPRECATED facade) = 1
- `knowledge_agent/routes.py`: 1 (FastAPI Depends, CORRECT) = 1
- `translation_agent/routes.py`: 1 (FastAPI Depends, CORRECT) = 1

---

## Test Resultaten

```
tests/unit/agents/test_agent_repository_protocol.py  5/5 PASSED
tests/unit/agents/test_agent_repository_isolation.py 1/1 PASSED
Regressie baseline: 365 passed (359 + 6 nieuwe), 0 failed
```

---

## Kwaliteitscheck

- `python -m pyright src/core/shared/interfaces.py src/core/database/agent_repository.py src/core/agents/base_agent.py` -> 0 errors
- `ruff check` (geen nieuwe violations)
- Tenant isolatie: beide methodes bevatten verplichte `WHERE tenant_id = ?` clause
- Paginering: alle list-methodes hebben `limit=50, offset=0` defaults
- Geen datetime.now(), geen emoji, geen non-ASCII in code/comments

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
