# Backend Feature Specification

## Metadata

- Feature ID: BE-ADR023-003
- Feature naam: Prometheus-metrics op de routing-laag (AgentRouterAgent/MasterOrchestratorAgent)
- Status: APPROVED
- Auteur: Claude (Sonnet 5)
- Reviewer: code-reviewer subagent (APPROVED WITH MINOR NOTES) + quality-reviewer subagent (APPROVED WITH MINOR NOTES) -- beide notes verwerkt vóór commit
- Datum: 2026-07-06
- Gerelateerde user story / ticket: SP-ADR023-002 Dag 3
- Gerelateerde router / module: `src/core/observability/metrics.py`, `src/core/agents/agent_router_agent.py`, `src/core/agents/master_orchestrator_agent.py`
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: geen
- Versie: 1.0

---

## Doel en scope

### Doel

ADR-023 sectie 6 claimt p50/p95/p99-routing-metrics, maar `AgentRouterAgent.route()` en
`MasterOrchestratorAgent.process_task()` hadden 0 Prometheus-instrumentatie -- alleen
in-memory tellers via de bestaande `metrics()`-methoden, niet zichtbaar in Grafana/Prometheus.

### Correctie op de oorspronkelijke sprint-dag-3-brief

De gegenereerde brief (`docs/agent-briefs/generated/2026-07-06-sprint-dag-3-SP-ADR023-002.md`)
stelde voor de metrics inline in `agent_router_agent.py` te definieren via de private
helpers `_get_or_create_counter`/`_get_or_create_histogram`. Geverifieerd tegen de code
vóór implementatie (zelfde discipline als Dag 1/2): het bestaande, al gebruikte precedent
(`src/core/agents/critic_agent.py`, SP-AGT-007) doet dit ANDERS -- de metric-objecten
worden gedefinieerd als module-level constanten IN `src/core/observability/metrics.py`
zelf, en de consumerende module importeert het kant-en-klare object. Dit plan volgt dat
gevestigde patroon, niet de oorspronkelijke briefsuggestie.

### In scope

**1. `src/core/observability/metrics.py`** -- nieuwe sectie "AgentRouterAgent /
MasterOrchestratorAgent Metrics", 3 metric-objecten:

| Metric | Type | Labels |
| --- | --- | --- |
| `sanskritisetu_agent_router_decision_latency_seconds` | Histogram | `tenant_id`, `tier` |
| `sanskritisetu_agent_router_cache_result_total` | Counter | `tenant_id`, `tier`, `result` |
| `sanskritisetu_master_orchestrator_workflow_duration_seconds` | Histogram | `tenant_id`, `status` |

`tier` in `{in_memory, redis, discovery, capability, llm, fallback}`, `result` in
`{hit, miss}`, `status` in `{succeeded, partial, failed}` -- alleen begrensde
cardinaliteit, geen taak-ID/agent-ID in labels.

**2. `AgentRouterAgent.route()`** -- instrumentatie op elk van de 6 resolverende paden,
expliciet per branch vlak voor de `return` (bewust GEEN gedeelde `finally` met een
tier-variabele -- na de Dag-2-les over "geconstrueerd maar nooit aangeroepen" is
per-branch instrumentatie visueel auditeerbaar). Cache-resultaat-counter `.inc()` bij de
in-memory-check en de Redis-check (laatste alleen als `_redis_cache_tier` geconfigureerd is).

**3. `MasterOrchestratorAgent.process_task()`** -- instrumentatie op zowel de succes-return
(dekt `succeeded` EN `partial`, want beide delen dezelfde return-tak via `plan.status.value`)
als het `except`-blok (`status=WorkflowStatus.FAILED.value`).

**4. `clear_tenant_cache()` concurrency-vangnet** -- geen productiecode-wijziging, alleen
een nieuwe test die het bestaande, al gedocumenteerde non-atomaire gedrag vastlegt
(`dependencies.py:118-124` NOTE).

### Gate-2-reviewbevindingen verwerkt vóór implementatie

- **code-reviewer**: ontbrekende testcase voor het geval dat een in-memory-cache-hit
  overloaded is (`current_load >= 0.9`) en doorvalt -- moet GEEN valse
  `tier="in_memory"`-observatie geven. Toegevoegd:
  `test_route_does_not_emit_in_memory_latency_when_cache_hit_is_overloaded`.
- **code-reviewer**: ontbrekende testcase voor `WorkflowStatus.PARTIAL` -- alleen
  `succeeded`/`failed` waren gedekt. Toegevoegd:
  `test_process_task_observes_duration_on_partial_success`.
- **quality-reviewer**: ontbrekende testcase die bewijst dat de Redis-"miss"-counter NIET
  vuurt wanneer `_redis_cache_tier is None` (geen Redis geconfigureerd). Toegevoegd:
  `test_route_does_not_increment_redis_cache_counter_when_tier_absent`.
- **quality-reviewer**: aanbeveling om `WorkflowStatus.FAILED.value` te gebruiken i.p.v.
  een losse string `"failed"` in het except-pad, voor drift-veiligheid. Overgenomen in de
  implementatie (test blijft de raw string `"failed"` gebruiken, wat vandaag equivalent is).

### Out of scope (vervalt aan volgende dagen/backlog)

- `route_with_fallback_chain()` (aparte fallback-chain-methode, niet aangeroepen door
  `route()`) blijft ongeinstrumenteerd -- bewuste scope-grens, geen omissie.
- OpenTelemetry-tracing (spans) op de routing-laag -- niet vandaag, ADR-014 dekt dit apart.

---

## Build summary

- Gewijzigd: `src/core/observability/metrics.py` (+3 metric-objecten)
- Gewijzigd: `src/core/agents/agent_router_agent.py` (import + instrumentatie `route()`)
- Gewijzigd: `src/core/agents/master_orchestrator_agent.py` (import + instrumentatie `process_task()`)
- Nieuw: `tests/unit/agents/test_agent_router_metrics.py` (9 tests)
- Nieuw: `tests/unit/agents/test_master_orchestrator_metrics.py` (3 tests)
- Nieuw: `tests/unit/api/orchestration/test_clear_tenant_cache_concurrency.py` (1 test, documenteert bestaand gedrag, geen productiewijziging)

---

## Testdekking

- Elk van de 6 resolverende tiers in `route()` observeert de latency-histogram met de
  juiste `tier`-label.
- De cache-resultaat-counter registreert `hit`/`miss` correct voor zowel de in-memory- als
  de Redis-tier, inclusief het geval dat de Redis-tier niet geconfigureerd is (geen
  `tier="redis"`-observatie in dat geval).
- De overloaded-in-memory-cache-hit-fallthrough triggert GEEN valse `tier="in_memory"`-observatie.
- `process_task()` observeert de workflow-duration-histogram op alle 3 statuswaarden
  (`succeeded`, `partial`, `failed`).
- `clear_tenant_cache()`'s bestaande non-atomaire gedrag is vastgelegd als regressietest.

Volledige gerichte regressie (`tests/unit/agents/`, `tests/unit/api/orchestration/`,
`tests/architecture/`, `tests/unit/test_agent_router_agent.py`): 903 passed, 0 failed
(nulpunt was 890; +13 nieuwe tests, geen regressies).

Gate 3: `python -m pyright` 0 errors (baseline gehandhaafd), `python -m mypy` op de 3
gewijzigde bronbestanden: success, `ruff check`: alle checks passed.

---

## Bekende beperkingen (bewust)

- `route_with_fallback_chain()` blijft ongeinstrumenteerd (aparte scope-grens, zie boven).
- Eerste-aanmaak-wint-semantiek van de singleton-factories (Dag 1/2) is ongewijzigd --
  metrics-instrumentatie zit in de instance-methoden, niet in de factory, dus dit gat
  is niet van toepassing op deze feature.
