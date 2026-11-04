# BE-AGT-009: AIContextEngine Wiring in CopilotService (SP-AGT-003)

**Status:** IMPLEMENTED
**Sprint:** SP-AGT-003 Dag 1
**ADR:** ADR-034 (agent_runtime service boundary), ADR-027 §11-14

---

## Summary

Wires `AIContextEngine` as the primary enrichment path in `CopilotService.handle_turn()`,
replacing the direct `ITwinService.get_profile()` call. The `twin_service` path becomes an
`elif` fallback for backwards compatibility.

## Scope

| File | Change |
|------|--------|
| `src/core/copilot/protocols.py` | Added `IAIContextEngine(Protocol)` |
| `src/core/copilot/service.py` | Added `context_engine` param + `handle_turn()` wiring |
| `src/core/copilot/dependencies.py` | Injects `AIContextEngine(db, require_tenant_id())` |
| `src/core/agents/context_engine.py` | Fixed log: removed raw exc from format string |
| `tests/unit/copilot/test_ai_context_engine_wiring.py` | 5 unit tests (RED -> GREEN) |
| `tests/architecture/test_sp_agt_003_context_engine_wiring.py` | 5 arch tests (GREEN) |

## Behaviour

**Before:** `CopilotService.handle_turn()` called `twin_service.get_profile()` directly
(ADR-034 violation — domain service imported into API-adjacent layer).

**After:** `context_engine.enrich(agent_id, query, surface)` is called first.
`EnrichedContext.context` is merged into `augmented_context` (top-level keys);
`EnrichedContext.twin_profile` is placed at `augmented_context["twin_profile"]`.
If `context_engine` is `None`, falls back to `twin_service.get_profile()`.
If `enrich()` raises, logs warning and continues (graceful degradation).

## Protocol

```python
class IAIContextEngine(Protocol):
    async def enrich(self, agent_id: str, query: str, surface: str) -> EnrichedContext: ...
```

Located in `src/core/copilot/protocols.py` alongside `IToolBroker`, `ITwinService`, etc.

## Injection

`_build_copilot_service()` in `dependencies.py` constructs:
```python
context_engine = AIContextEngine(db=db, tenant_id=require_tenant_id())
```
`require_tenant_id()` (not `get_tenant_id()`) — raises RuntimeError if tenant context
missing (fail-secure per ADR-003).

## Tests

| Test | Type | Covers |
|------|------|--------|
| `test_copilot_service_accepts_context_engine_parameter` | unit | __init__ signature |
| `test_handle_turn_calls_context_engine_enrich` | unit | enrich() called |
| `test_enriched_context_data_flows_into_llm_context` | unit | context flows to LLM |
| `test_handle_turn_graceful_when_context_engine_raises` | unit | graceful degradation |
| `test_twin_service_not_called_directly_when_context_engine_present` | unit | security: no bypass |
| `test_iai_context_engine_protocol_defined_in_protocols` | arch | protocol location |
| `test_copilot_service_has_context_engine_parameter` | arch | __init__ signature |
| `test_handle_turn_calls_context_engine_before_twin_service` | arch | ordering invariant |
| `test_dependencies_injects_context_engine` | arch | DI wiring |
| `test_context_engine_log_does_not_leak_exception_message` | arch | log security |

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
