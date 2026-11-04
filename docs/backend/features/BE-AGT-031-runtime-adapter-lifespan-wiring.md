# BE-AGT-031: MasterOrchestratorRuntimeAdapter + Lifespan Wiring

**ID:** BE-AGT-031
**Sprint:** SP-AGT-001 Dag 2
**ADR:** ADR-034 (agent_runtime service boundary)
**Status:** IMPLEMENTED (updated Dag 3: hardening)
**Datum:** 2026-06-09

---

## Doel

Na Dag 1 bestond `src/core/agents/api.py` als lege facade: `get_agent_runtime()` gooide altijd een
`RuntimeError` omdat er nooit een concrete implementatie werd geregistreerd.

Dag 2 maakt de facade operationeel:
1. `MasterOrchestratorRuntimeAdapter` implementeert `IAgentRuntime` via delegation naar `MasterOrchestratorAgent`.
2. De adapter wordt bij startup geregistreerd via `register_agent_runtime()` in de app lifespan.

---

## Gecreeerde/gewijzigde bestanden

| Bestand | Type | Omschrijving |
|---------|------|--------------|
| `src/core/agents/runtime_adapter.py` | Nieuw | Adapter klasse (~32 regels) |
| `src/core/api/main.py` | Gewijzigd | Lifespan wiring: `register_agent_runtime()` aangeroepen bij startup |

---

## Implementatie

### `MasterOrchestratorRuntimeAdapter`

Thin delegation-laag zonder business-logica:

- `orchestrate(task)` -- delegeert naar `MasterOrchestratorAgent.process_task(task)`
- `route(task)` -- delegeert ook naar `process_task(task)` tot SP-AGT-002 `AgentRouterAgent` wiret
- `get_health()` -- retourneert `{"status": "healthy", "agent": ..., "capabilities": N}`

Voldoet structureel aan `IAgentRuntime` Protocol (`@runtime_checkable`): `isinstance(adapter, IAgentRuntime) is True`.

### Lifespan wiring (main.py)

```python
orchestrator = get_master_orchestrator(tenant_id=1)
await orchestrator.initialize()  # fail fast bij startup ipv eerste request
register_agent_runtime(MasterOrchestratorRuntimeAdapter(orchestrator))
```

- `tenant_id=1` is de system-level bootstrap instance; per-tenant routing via `task.tenant_id`.
- `try/except` wrapping: wiring-fout blokkeert niet de volledige startup.
- `await orchestrator.initialize()`: LLM-client setup bij startup (fail fast).

---

## Pre-existing completions

| Gap | Sprint | Status |
|-----|--------|--------|
| CG-005: health write bridge | SP-WE-10 | REEDS OPGELOST (4/4 tests PASS) |
| CG-006: CriticMixin wiring in MasterOrchestratorAgent | SP-WE-11 | REEDS OPGELOST (8/8 tests PASS) |

Geen werk nodig voor Dag 2.

---

## DSM meting

| Meting | Methode | Waarde |
|--------|---------|--------|
| Baseline (aanvang SP-AGT-001) | `dsm_full_analysis.py` (totale fan-out) | 621 |
| Na Dag 1 + Dag 2 | grep: bestanden die `src.core.agents.*` importeren | 119 |

Noot: de twee methoden zijn niet direct vergelijkbaar. De grep-meting telt bestanden (niet import-edges).
Een geconsisteerde meting volgt in Dag 3 (sprint-retrospectief).

---

## Testbewijs

```
tests/unit/agents/test_runtime_adapter.py  -- 6/6 PASS
tests/unit/agents/test_agents_facade.py    -- 6/6 PASS
tests/architecture/test_adr034_contracts.py -- 3/3 PASS

Totaal 15 tests PASS.
Regressiecheck: 374 passed, 0 failed (tests/unit/agents/ + tests/architecture/).
```

---

## Dag 3 hardening (2026-06-09)

- `get_health()` weerspiegelt echte LLM-staat: `"degraded"` als `llm_client is None`, `"healthy"` anders; `llm_ready: bool` toegevoegd aan response.
- Lifespan: `initialize()` return waarde gecontroleerd; facade wordt NIET geregistreerd bij `False` (log warning in plaats van silent broken registration).
- `master_orchestrator_agent.py:181`: `logger.error` voorzien van `type(exc).__name__` + `exc_info=True` per backend-pattern 10.
- 3 nieuwe tests toegevoegd: `route()` delegation, `get_health()` degraded path, `get_health()` healthy path.

**Testbewijs na Dag 3:**

```text
tests/unit/agents/test_runtime_adapter.py  -- 9/9 PASS
tests/unit/agents/test_agents_facade.py    -- 6/6 PASS
tests/architecture/test_adr034_contracts.py -- 3/3 PASS

Regressiecheck: 377 passed, 0 failed (agents/ + architecture/)
```

## Review

Zie `docs/backend/review/review-BE-AGT-031.md`.


## Trainingssamenvatting

- Actor: De app-lifespan startup-code in `src/core/api/main.py` en callers van de agent-runtime facade.
- Voorwaarde: App start op; Redis-client en database-session factory zijn beschikbaar; `register_agent_runtime` en `MasterOrchestratorRuntimeAdapter` zijn importeerbaar.
- Actie (request): Startup haalt `redis_client = await get_redis_client()`, bouwt `orchestrator = get_master_orchestrator(tenant_id=1, async_session_factory=get_db_session, redis_client=redis_client)`, roept `init_ok = await orchestrator.initialize()` aan, en registreert bij succes `register_agent_runtime(MasterOrchestratorRuntimeAdapter(orchestrator))`. Na startup kunnen callers `get_agent_runtime()` gebruiken en `await runtime.orchestrate(task)`, `await runtime.route(task)` of `await runtime.get_health()` aanroepen.
- Systeemverwerking: `MasterOrchestratorRuntimeAdapter` delegeert `orchestrate(task)` en `route(task)` aan `MasterOrchestratorAgent.process_task(task)`. `get_health()` vraagt capabilities op, controleert of `llm_client` is gezet, en retourneert `status`, `agent`, `capabilities` en `llm_ready`.
- Succesrespons: Na startup is de facade geregistreerd; `orchestrate`/`route` retourneren een `ExecutionResult`; `get_health()` retourneert een dict met `status: "healthy"` of `"degraded"`.
- Foutrespons: Als `initialize()` `False` retourneert, wordt de facade NIET geregistreerd en logt de startup een warning; laten calls naar `get_agent_runtime()` resulteren in `RuntimeError`. Bij een exception tijdens wiring wordt een error gelogd en startup gaat door (non-fatal).
- Uitzonderingen: `route()` delegeert tijdelijk ook naar `process_task()` omdat `AgentRouterAgent` nog niet direct is gewired; tenant_id=1 is de system-bootstrap instance, per-tenant routing gebeurt later via `task.tenant_id`.
