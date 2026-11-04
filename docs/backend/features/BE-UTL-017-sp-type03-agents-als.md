# BE-UTL-017 — Sp Type03 Agents Als

**ID:** BE-UTL-017
**Sprint:** SP-TYPE-03 Dag 2-9
**Type:** Utility (type refactoring)
**Status:** CLOSED — commit `4f43ed1a`
**Bestanden:** src/core/agents/performance_optimizer.py, src/core/agents/workflow_orchestrator_agent.py, src/core/agents/executor_agent.py, src/core/agents/cva_agent.py, src/core/agents/base_agent.py, src/core/als/router.py, src/core/als/models/collective_knowledge.py, src/core/agents/ethical_knowledge_graph.py, src/core/agents/subagent_loader.py, src/core/agents/corrective_rag_agent.py, src/core/agents/resilient_api_client.py, + 11 small agent/als files

---

## Samenvatting

Full type hardening across agent implementations and ALS (Agent Learning System) models.

---

## Wijzigingen

BaseSandboxManager|None, aiohttp.ClientSession|None, dict[str,LLMClient], list[AgentDefinition], list[KnowledgeRelationship], list[tuple[str,float]], asyncio.Task[None], ExecutionResult, Callable[[TaskData],ExecutionResult].

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
