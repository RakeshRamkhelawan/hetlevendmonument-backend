# BE-DSM-016: SP-DSM-006 Dag 2 -- agent_runtime fan-out 878->800

**Sprint**: SP-DSM-006 Dag 2
**Datum**: 2026-06-17
**Status**: APPROVED

## Probleemstelling

Cross-module fan-out van `agent_runtime` was 878 (Grade A+ budget: 500, XFAIL in CI).
Dag 2 doel: reduceren via shim-patroon analoog aan SP-DSM-002 cluster-aanpak.

## Oplossing

### Cluster B: LLM imports (Batch 1 + Batch 2)

**Shim `src/core/agents/llm_types.py` aangemaakt** met re-exports van
`src.core.llm.agent_model_matcher`. Twee batches:

- **Batch 1**: 73 gegenereerde agents (`src/core/agents/generated/*.py`) --
  allen hadden dezelfde function-local import `AgentCategory, AgentProfile, TaskComplexity`.
  Bulk-replaced naar shim via sed. Reductie: -69 (73 weg, shim telt 1 terug als llm).

- **Batch 2**: 8 niet-gegenereerde bestanden (marketing_agent, product_agent,
  master_orchestrator_agent, agent_health_monitor_agent, agent_router_agent,
  agent_factory) + shim uitgebreid met `TaskCharacteristics` en `agent_model_matcher`.
  Reductie: -9.

**Totale reductie**: 878 -> 800 (-78).

## Structurele bevinding (voor Rakesh + Dag 3 scope)

Na volledige analyse is de samenstelling van de 800:

| Bucket | Imports | Reduceerbaarheid |
|--------|---------|-----------------|
| shared | 481 | LAAG -- foundation types (ExecutionResult 173x, AgentType 102x) |
| infra | 153 | LAAG -- ORM Base (20x), db_manager (18x), get_db (8x) |
| llm | 34 | MEDIUM -- diverse providers, gedeeltelijk reduceerbaar |
| integrations | 30 | LAAG -- merendeels by design |
| governance | 30 | GEEN -- ADR-027 copilot->governance by design |
| tenancy | 23 | GEEN -- ADR-003 get_tenant_id verplicht |
| auth | 18 | GEEN -- security-kritisch |
| tool_broker | 16 | LAAG |
| domain_pack | 11 | LAAG |

**Subtotaal locked (shared + infra + governance + tenancy + auth)**: 705

**Conclusie**: Grade A+ budget van 500 is NIET haalbaar zonder:
1. Reclassificatie van `src.core.shared.interfaces` en `src.core.types` van
   "shared" naar "agent_runtime" in MODULE_MAP (beleidsbeslissing Rakesh)
2. Of: Structurele verplaatsing van foundation-types naar agent_runtime

De werkelijk reduceerbare ruimte (llm + tool_broker + domain_pack) is ~60.
Maximum bereikbaar: 800 - 60 = ~740. Budget van 500 vereist structurele MODULE_MAP-aanpassing.

## Bestanden gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/llm_types.py` | NIEUW: re-export shim voor agent_model_matcher types |
| `src/core/agents/generated/*.py` (73 bestanden) | Bulk-replace llm -> llm_types shim |
| `src/core/agents/marketing_agent.py` | 2 imports -> shim |
| `src/core/agents/product_agent.py` | 2 imports -> shim |
| `src/core/agents/master_orchestrator_agent.py` | 1 import -> shim |
| `src/core/agents/agent_health_monitor_agent.py` | 1 import -> shim |
| `src/core/agents/agent_router_agent.py` | 1 import -> shim |
| `src/core/agents/agent_factory.py` | 1 import -> shim |

## Verificatie

```
Cross-module fan-out: 878 -> 800 (-78)
pytest tests/architecture/: 158 passed, 17 xfailed, 0 failed
python -m pyright: 0 errors (baseline ongewijzigd)
ruff check <gewijzigde bestanden>: All checks passed
Gerichte regressie (agent bestanden): 0 failures
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-006 Dag 2: agent_runtime fan-out 878->800 (-78). llm_types.py shim + 73 generated agents + 8 orchestrators via shim. Structurele bevinding: 705 locked (shared+infra+by-design). Budget 500 vereist MODULE_MAP-aanpassing. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-006 Dag 2: agent_runtime fan-out 878->800 (-78). llm_types.py shim + 73 generated agents + 8 orchestrators via shim. Structurele bevinding: 705 locked (shared+infra+by-design). Budget 500 vereist MODULE_MAP-aanpassing..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
