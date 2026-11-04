# BE-AGT-033 — Business Task Tool (Dag 3)

> Sprint: **AGENTIC-COPILOT-TAAKBEHEER-2026-07**  
> Datum: 2026-07-06  
> Samenhangende IDs: `BE-AGT-033`, `BE-SEC-032`, `BE-SEC-033`  
> Scope: ToolBroker-uitvoerlaag voor `create_task` en `list_tasks`. Geen endpoints, geen HITL/audit/delete (dag 4), geen frontend (fase B).

---

## A. Build Summary

Dag 3 sluit het gat dat de Council een taakactie (`create_task`, `list_tasks`) wel kan goedkeuren, maar dat de ToolBroker deze weigert met "Unknown tool category". Het werk omvat:

- Een nieuwe `BusinessToolRegistry` in `src/core/tool_broker/business_registry.py` die Council action_types afhandelt door `TaskService` aan te roepen.
- Uitbreiding van `ToolBrokerService.execute_tool` zodat `create_task` en `list_tasks` worden herkend en naar de registry worden doorgeschoven.
- Configuratie-updates in `config/tool_permissions.yml` en `src/core/config/tool_risk_levels.yml`.
- Unit-tests die het gat reproduceren en de fix verifiëren, plus PostgreSQL-integratietests die echte rijen in `agentic_tasks` schrijven en lezen.

---

## B. Backend Inventory

| ID | Naam | Type | Locatie |
| --- | --- | --- | --- |
| BE-AGT-033 | BusinessToolRegistry | Tool registry | `src/core/tool_broker/business_registry.py` |
| BE-AGT-033 | ToolBrokerService business-tool dispatch | Service | `src/core/tool_broker/service.py` |
| BE-SEC-032 | Tool permission profiles (copilot mag create/list) | Config | `config/tool_permissions.yml` |
| BE-SEC-033 | Tool risk levels (create_task medium, list_tasks low) | Config | `src/core/config/tool_risk_levels.yml` |
| BE-TSK-012 | Unit tests business task tools | Test | `tests/unit/tool_broker/test_business_task_tool.py` |
| BE-SEC-034 | Integratietest business task tools (echte DB) | Test | `tests/integration/tool_broker/test_business_task_tool.py` |

Ook gewijzigd:

- `src/core/tool_broker/service.py` — business-tool categorieherkenning en dispatch.

---

## C. Functionele specificatie

### C.1 BusinessToolRegistry (BE-AGT-033)

**Doel**  
Bridge tussen ToolBroker action_types en de Dag-2 `TaskService`, zodat een Council-goedgekeurde `create_task` echt een rij in `agentic_tasks` aanmaakt.

**Functionele beschrijving**  
De registry is een zelfstandige component zonder afhankelijkheid van de Council. Ze krijgt een tool-naam en payload, extraheert `tenant_id` uit de payload (die door `ToolBrokerService.execute_tool` uit de aanroepcontext is geinjecteerd), opent een tenant-scoped database-sessie en roept `TaskService` aan.

**Ondersteunde tools**

| Tool | Risico | Gedrag |
| --- | --- | --- |
| `create_task` | medium | Maakt een task aan via `TaskService.create(TaskCreate(**payload))`. |
| `list_tasks` | low | Lijst taken via `TaskService.list(status, assigned_agent_id, skip, limit)`. |

**Tenant-isolatie**

- `tenant_id` komt uit de ToolBroker-context en wordt altijd over de eventuele payload-waarde heen geschreven.
- De registry zet de tenant ContextVar zodat `db_manager.get_session()` de RLS-context correct instelt.
- `TaskService` krijgt `tenant_id` expliciet mee in de constructor; de payload wordt ontdaan van `tenant_id`, `user_id`, `decision_id` en `id` vóór schema-validatie.

**Foutafhandeling**

- Ontbrekende `tenant_id` -> `ToolExecutionException("tenant_id is required ...")`.
- Onbekend business-tool-naam -> `ToolExecutionException("Business tool '...' is not implemented")`.
- Ongeldige task-data -> `ToolExecutionException("Invalid task data: ...")`.

### C.2 ToolBrokerService dispatch

**Wijzigingen**

1. `_known_prefixes` controle wordt uitgebreid: naast de bestaande prefixes worden `create_task` en `list_tasks` geaccepteerd.
2. Na de `local__` / `test__` tak wordt een business-tool tak toegevoegd vóór de Serena / Sequential Thinking dispatch.
3. Bestaande serena/local/sequentialthinking-paden zijn ongewijzigd (additief).

**Resultaat-contract**

```json
{"success": true, "data": <TaskRead dict>}
{"success": true, "data": [<TaskRead dict>, ...], "count": N}
```

### C.3 Configuratie

**`config/tool_permissions.yml`**

- `copilot` profiel krijgt `"list_tasks"` toegevoegd ( `"create_task"` was al aanwezig).

**`src/core/config/tool_risk_levels.yml`**

- `create_task: medium`
- `list_tasks: low`

Dit voorkomt dat de tools als HIGH worden geclassificeerd en een HITL-ticket eisen.

---

## D. Dataflow

```text
CopilotService
    |
    v
_tool_broker.execute_tool(
    tool_name="create_task",
    payload={"title": "Review audit"},
    agent_id="copilot",
    context={"tenant_id": 1, "user_id": 2, "decision_id": "..."}
)
    |
    v
ToolBrokerService.execute_tool
    |
    +-- injecteert tenant_id/user_id in payload
    +-- ToolPermissionManager.is_tool_allowed("copilot", "create_task") -> True
    +-- ToolRiskClassifier.classify("create_task") -> medium
    +-- dispatch naar BusinessToolRegistry.execute_business_tool
            |
            v
    BusinessToolRegistry
            |
            +-- extract tenant_id
            +-- set_tenant_id(tenant_id)
            +-- async with db_manager.get_session() as session:
                    TaskService(session, tenant_id).create(TaskCreate(...))
            |
            v
    {"success": true, "data": TaskRead(...)}
```

---

## E. Acceptatiecriteria

- [x] `ToolBrokerService.execute_tool("create_task", ...)` maakt een echte rij in `agentic_tasks`.
- [x] `ToolBrokerService.execute_tool("list_tasks", ...)` retourneert taken van de aanroepende tenant.
- [x] `ToolBrokerService.execute_tool("list_tasks", ...)` voor tenant B toont geen taken van tenant A.
- [x] `ToolBrokerService.execute_tool("update_task", ...)` faalt nog steeds met "Unknown tool category" (buiten scope vandaag).
- [x] `ToolBrokerService.execute_tool("serena__...", ...)` en `local__...` blijven ongewijzigd werken.
- [x] `create_task` zonder `tenant_id` in context/payload faalt fail-secure.
- [x] Een `tenant_id` in de payload wordt nooit boven de context-tenant geplaatst.
- [x] `list_tasks` weigert ongeldige `skip`/`limit` waarden met een duidelijke foutmelding.
- [x] Onbekende agent krijgt "Permission denied" (default-deny).
- [x] Architecture-suite blijft 382 passed / 0 failed.
- [x] Unit- en integratietests voor de nieuwe tool-laag zijn groen.

---

## F. Trainingssamenvatting

### Flow: copilot maakt een taak aan via create_task

- Actor: De copilot-agent (via `_ToolBrokerAdapter` -> `ToolBrokerService`).
- Voorwaarde: De gebruiker is geauthenticeerd; `ToolBrokerService` is geinitialiseerd met `business_registry` en `permission_manager`; `config/tool_permissions.yml` staat `copilot` toe om `create_task` te gebruiken; `src/core/config/tool_risk_levels.yml` classificeert `create_task` als medium.
- Actie (request): `ToolBrokerService.execute_tool(tool_name="create_task", payload={"title": "Review audit"}, agent_id="copilot", context={"tenant_id": 1, "user_id": 2, "decision_id": "..."})`.
- Systeemverwerking: `ToolBrokerService` injecteert `tenant_id` en `user_id` uit de context in de payload; `ToolPermissionManager` controleert of `copilot` `create_task` mag gebruiken; `ToolRiskClassifier` bepaalt dat het MEDIUM-risk is (geen HITL vereist); de aanroep wordt doorgeschoven naar `BusinessToolRegistry.execute_business_tool`; deze extraheert `tenant_id`, zet de tenant ContextVar, opent een DB-sessie via `db_manager.get_session()`, maakt een `TaskCreate` van de payload en roept `TaskService.create()` aan.
- Succesrespons: `{"success": true, "data": {"id": "...", "title": "Review audit", "status": "todo", "tenant_id": 1, ...}}`.
- Foutrespons: `ToolExecutionException` met detail "Permission denied: Agent 'copilot' is not authorized to use tool 'create_task'" als de tool niet in het profiel staat, of "Invalid task data: ..." bij een validatiefout.
- Uitzonderingen: Een `tenant_id` in de payload wordt overschreven door de context-tenant om cross-tenant spoofing te voorkomen; ontbrekende `tenant_id` levert "tenant_id is required in tool payload/context".

### Flow: copilot vraagt taken op via list_tasks

- Actor: De copilot-agent (via `_ToolBrokerAdapter` -> `ToolBrokerService`).
- Voorwaarde: Zelfde als create_task, maar `list_tasks` staat als low-risk geclassificeerd.
- Actie (request): `ToolBrokerService.execute_tool(tool_name="list_tasks", payload={"status": "todo", "limit": 50}, agent_id="copilot", context={"tenant_id": 1, "user_id": 2})`.
- Systeemverwerking: Permission check en risk classificatie verlopen; `BusinessToolRegistry` parsed `skip`/`limit` met defaults en grenzen, opent een tenant-scoped sessie en roept `TaskService.list(status, assigned_agent_id, skip, limit)` aan.
- Succesrespons: `{"success": true, "data": [{"id": "...", "title": "...", ...}], "count": N}`.
- Foutrespons: `ToolExecutionException` met detail "limit must be <= 1000, got ..." of "skip must be >= 0, got ..." bij ongeldige paginatie.
- Uitzonderingen: `list_tasks` toont alleen taken van de tenant die in de context zit; RLS en repository-filter worden beide toegepast.
