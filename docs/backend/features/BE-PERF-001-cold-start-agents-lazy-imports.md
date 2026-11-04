# BE-PERF-001: SP-PERF-001 -- Agents Router Lazy Imports (ADR-009 cold-start)

**Sprint:** SP-PERF-001
**Status:** APPROVED
**Datum:** 2026-06-21

---

## Samenvatting

Lazy imports toegepast op de agents router-laag om ADR-009 dev startup budget (<30s) te halen.
Bottleneck: `AgentRegistry` en gerelateerde zware modules werden bij module-import geladen.

---

## Wijzigingen

### src/core/api/v1/agents/dependencies.py

`AgentRegistry` verplaatst van top-level import naar:
- `TYPE_CHECKING` guard voor type-annotaties
- Lazy import in `get_agent_registry_dependency()` body

`RegisteredAgent` verwijderd uit facade `__all__` (ongebruikt door callers).

### src/core/api/v1/agents/agent_crud_router.py

`from __future__ import annotations` toegevoegd.
`AgentRegistry` onder `TYPE_CHECKING`; string-annotatie in Depends-signatuur.

### src/core/api/v1/agents/agent_execution_router.py

Zelfde patroon als agent_crud_router.

### src/core/api/v1/agents/agent_management_router.py

Zelfde patroon als agent_crud_router.

### src/core/api/agent_endpoints.py

`AgentRegistry`, `RegisteredAgent`, `AgentRegistryRepository`, `get_settings` lazy gemaakt.
`get_activepieces_service` verwijderd uit top-level imports (lazily resolved in handler).

### tests/unit/test_agent_endpoints.py

Patch-targets gecorrigeerd voor twee tests:
- `src.core.api.agent_endpoints.get_settings` -> `src.core.shared.config.get_settings`
- `src.core.api.agent_endpoints.get_activepieces_service` -> `src.core.activepieces.service.get_activepieces_service`

---

## Tests

| Testbestand | Resultaat |
|-------------|-----------|
| `tests/unit/api/v1/agents/test_agent_router_lazy_import.py` | 2 PASS |
| `tests/unit/test_agent_endpoints.py` | 19 passed, 3 xfailed |

Lazy import test verifieert dat `AgentRegistry` NIET geimporteerd wordt bij module-load van de agents router.

---

## Trainingssamenvatting

- Actor: dev server startup
- Voorwaarde: backend start op, router registratie begint
- Actie: agents sub-router module wordt geladen
- Systeemreactie: module laadt zonder `AgentRegistry` te importeren
- Succes: eerste request trigger lazy import -- geen startup penalty
- Fout: n.v.t.

---

## Gate 3

- `python -m pyright`: 0 errors (baseline behouden)
- `ruff check src/core/api/v1/agents/ src/core/api/agent_endpoints.py`: clean
