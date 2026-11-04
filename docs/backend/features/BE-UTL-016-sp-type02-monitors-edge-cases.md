# BE-UTL-016 — Sp Type02 Monitors Edge Cases

**ID:** BE-UTL-016
**Sprint:** SP-TYPE-02 Dag 9
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `d8ead362`
**Bestanden:** src/core/copilot/proactive/monitors/*.py (11), src/core/learning/interfaces/llm_provider.py, src/core/llm/deepseek_provider.py, src/core/llm/local_provider.py, src/core/observability/audit_logger.py, src/core/learning/cache.py, src/core/learning/experiment_tracker.py, src/core/learning/analytics.py, src/core/services/rbac_service.py

---

## Samenvatting

Proactive monitors cleanup and remaining edge cases in LLM, observability, learning, and RBAC.

---

## Wijzigingen

Legacy imports removed from 11 monitor files. list[Role] for get_user_roles, dict[str,tuple[bool,float]] for perm_cache, list[float] for analytics, dict[str,float] for metrics.

---

## Trainingssamenvatting

**Flow: Type-annotatie refactoring**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety sprint agent (SP-TYPE-04 workflow) |
| Voorwaarde | Bestanden bevatten `Any` annotaties zonder TODO of met TODO als baseline |
| Actie | HIGH-confidence type replacements via gestructureerde analyse |
| Systeemverwerking | Parallel analyse -> apply -> TDD tests -> ruff -> commit |
| Succesrespons | TDD tests groen, ruff 0 errors |
| Foutrespons | Revert bij ruff failure; skip bij niet-gevonden old_text |
| Uitzonderingen | *args:Any, **kwargs:Any, generic decorators, externe SDK types bewust als Any gelaten |
