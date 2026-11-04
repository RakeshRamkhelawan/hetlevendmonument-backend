# BE-UTL-015 — Sp Type02 Activepieces Resilience Services

**ID:** BE-UTL-015
**Sprint:** SP-TYPE-02 Dag 6-8
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `9e65ccb6`
**Bestanden:** src/core/activepieces/service.py, src/core/tool_broker/resilience.py, src/core/tool_broker/service.py, src/core/activepieces/client.py, src/core/resilience/circuit_breaker.py, src/core/resilience/retry_policy.py, src/core/middleware/performance_profiler.py, src/core/llm/fallback_chain.py, src/core/services/training_service.py, src/core/services/workflow_generator_service.py, src/core/services/focus_suggestion_service.py, src/core/llm/llm_service.py, src/core/llm/production_llm_client.py

---

## Samenvatting

Type hardening in activepieces, tool_broker, resilience, middleware, and services layer.

---

## Wijzigingen

errors: list[str], _call_model -> str|None, messages: list[dict[str,str]], PerformanceProfiler|None, AsyncSession|None, Settings, list[GhostNodeSuggestion], dict[str,float|int]. Legacy imports cleaned.

---

## Trainingssamenvatting

**Flow: Type-annotatie refactoring**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety sprint agent (SP-TYPE-04 workflow) |
| Voorwaarde | Bestanden bevatten `Any` annotaties zonder TODO of met TODO als baseline |
| Actie | HIGH-confidence type replacements via gestructureerde analyse |
| Systeemverwerking | Parallel analyse → apply → TDD tests → ruff → commit |
| Succesrespons | TDD tests groen, ruff 0 errors |
| Foutrespons | Revert bij ruff failure; skip bij niet-gevonden old_text |
| Uitzonderingen | *args:Any, **kwargs:Any, generic decorators, externe SDK types bewust als Any gelaten |
