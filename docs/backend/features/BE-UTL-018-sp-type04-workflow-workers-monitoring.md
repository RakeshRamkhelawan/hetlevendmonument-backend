# BE-UTL-018 — Sp Type04 Workflow Workers Monitoring

**ID:** BE-UTL-018
**Sprint:** SP-TYPE-04 Dag 2-4 Group A
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `5bdf93cf`
**Bestanden:** src/core/workflow/providers.py, src/workers/workflow_worker.py, src/workers/actors.py, src/core/monitoring/prometheus_metrics.py, src/core/workflow/worker.py, src/core/monitoring/vibe_monitoring.py

---

## Samenvatting

Type hardening in workflow providers, workers, and monitoring layer.

---

## Wijzigingen

AsyncEngine|None, async_sessionmaker[AsyncSession]|None, ILLMProvider/IToolBroker/IAgentRuntime interfaces, dict[str,str] for vibe monitoring (all string values provable), __aexit__ standard signatures.

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
