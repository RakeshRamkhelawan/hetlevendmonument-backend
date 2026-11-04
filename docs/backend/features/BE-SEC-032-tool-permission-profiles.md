# BE-SEC-032 — Tool Permission Profiles voor create_task/list_tasks

> Sprint: **AGENTIC-COPILOT-TAAKBEHEER-2026-07**  
> Datum: 2026-07-06  
> Samenhangende IDs: `BE-AGT-033`, `BE-SEC-032`, `BE-SEC-033`  
> Scope: Configuratie-wijziging in `config/tool_permissions.yml` en `src/core/config/tool_risk_levels.yml` zodat de copilot-agent `create_task` en `list_tasks` mag uitvoeren via ToolBroker.

---

## A. Build Summary

Dag 3 van het agentic-copilot-taakbeheer voegt de benodigde permission- en risk-level configuratie toe zodat `ToolBrokerService.execute_tool("create_task", ...)` en `"list_tasks"` niet meer worden geweigerd door `ToolPermissionManager` of verkeerd worden geclassificeerd als HIGH-risk/HITL-vereisend.

- Uitbreiding van `config/tool_permissions.yml`: het `copilot` profiel krijgt `create_task` en `list_tasks` in `allowed_tools`.
- Uitbreiding van `src/core/config/tool_risk_levels.yml`: `create_task` wordt medium, `list_tasks` low.
- Geen productiecode gewijzigd; de configuratie wordt op runtime gelezen door `ToolPermissionManager` respectievelijk `ToolRiskClassifier`.

---

## B. Backend Inventory

| ID | Naam | Type | Locatie |
| --- | --- | --- | --- |
| BE-SEC-032 | Tool permission profiles (copilot mag create/list/update/delete) | Config | `config/tool_permissions.yml` |
| BE-SEC-033 | Tool risk levels voor business task tools | Config | `src/core/config/tool_risk_levels.yml` |

---

## C. Functionele specificatie

### C.1 ToolPermissionManager default-deny allowlist

**Locatie**  
- Config: `config/tool_permissions.yml`  
- Consumer: `src/core/tool_broker/permission_manager.py` -> `ToolPermissionManager.is_tool_allowed()`

**Doel**  
Bepalen welke agent welke tool mag aanroepen. Niet-geregistreerde agents worden default denied (ADR-015).

**Wijziging**  
Het profiel voor agent `copilot` is uitgebreid met:

```yaml
agent_profiles:
  - agent_id: "copilot"
    allowed_tools:
      - ...bestaande tools...
      - "create_task"
      - "list_tasks"
      - "update_task"
      - "delete_task"
```

Dit dekt alle Council action_types die via `_ToolBrokerAdapter` naar `ToolBrokerService` worden doorgespeeld.

**Business rules**

- Een agent zonder profiel mag geen enkele tool gebruiken.
- Een tool die niet in `allowed_tools` staat, wordt geweigerd.
- `denied_tools` is expliciet leeg voor `copilot`; deze lijst kan worden gebruikt om een specifieke tool binnen een profiel te blokkeren zonder het hele profiel te verwijderen.
- `max_tools: 50` is een bovengrens voor het aantal tools dat in een enkel profiel mag staan.

### C.2 ToolRiskClassifier niveaus

**Locatie**  
- Config: `src/core/config/tool_risk_levels.yml`  
- Consumer: `src/core/tool_broker/risk_classifier.py` -> `ToolRiskClassifier.classify()`

**Doel**  
Bepalen welk HITL- en auditniveau een tool vereist.

**Wijziging**

```yaml
tool_risk_levels:
  create_task: medium
  list_tasks: low
  update_task: medium
  delete_task: high
```

**Resolutievolgorde**

1. Exacte match in `tool_risk_levels`.
2. Prefix-match in `tool_prefixes`.
3. `default_risk_level: high` als fallback.

Dit betekent dat `create_task` en `list_tasks` niet meer door de fallback als HIGH worden geclassificeerd.

**Business rules**

- `low`: read-only, direct uitvoerbaar.
- `medium`: write/update, wordt gelogd, geen HITL vereist.
- `high`: delete/admin, HITL-goedkeuring vereist (bijvoorbeeld `delete_task`).

---

## D. Technische beschrijving

`ToolBrokerService.execute_tool` roept in volgorde aan:

1. `self.permission_manager.is_tool_allowed(agent_id or "", tool_name)`  
   Leest `config/tool_permissions.yml`. Voor agent `copilot` en tool `create_task` retourneert dit `True`.
2. `self.risk_classifier.classify(tool_name)`  
   Leest `src/core/config/tool_risk_levels.yml`. Voor `create_task` retourneert dit `ToolRiskLevel.MEDIUM`.
3. Bij `MEDIUM` wordt geen HITL-ticket gecontroleerd; bij `HIGH` wel.

De YAML-bestanden worden lazy geladen; de eerste `execute_tool`-aanroep na startup parsed de configuratie. Fouten in de YAML leiden tot een duidelijke exception tijdens het laden.

---

## E. Foutafhandeling

- Ontbrekend `config/tool_permissions.yml` of `src/core/config/tool_risk_levels.yml` -> startup-time of first-call parse-error.
- Agent niet in profielen -> `ToolExecutionException("Permission denied: Agent '...' is not authorized to use tool '...'")`.
- Tool niet in `allowed_tools` -> zelfde permission-denied.
- `create_task`/`list_tasks` niet in `tool_risk_levels` -> fallback `high`, waardoor onterecht HITL wordt geëist.

---

## F. Acceptatiecriteria

- [x] `config/tool_permissions.yml` bevat `create_task`, `list_tasks`, `update_task`, `delete_task` in het `copilot` profiel.
- [x] `src/core/config/tool_risk_levels.yml` classificeert `create_task` als medium, `list_tasks` als low, `delete_task` als high.
- [x] `ToolBrokerService.execute_tool("create_task", ..., agent_id="copilot")` wordt niet meer geweigerd.
- [x] `ToolBrokerService.execute_tool("list_tasks", ..., agent_id="copilot")` wordt niet meer geweigerd.
- [x] `ToolBrokerService.execute_tool("delete_task", ..., agent_id="copilot")` eist nog steeds een goedgekeurde HITL-ticket.
- [x] Onbekende agent krijgt permission denied.

---

## G. Trainingssamenvatting

### Flow: copilot gebruikt create_task via ToolBroker

- Actor: De copilot-agent (bijvoorbeeld via `_ToolBrokerAdapter`).
- Voorwaarde: `config/tool_permissions.yml` is geladen en bevat een profiel voor agent `copilot` met `create_task` in `allowed_tools`; `src/core/config/tool_risk_levels.yml` bevat `create_task: medium`.
- Actie (request): `ToolBrokerService.execute_tool(tool_name="create_task", payload={"title": "..."}, agent_id="copilot", context={"tenant_id": 1, "user_id": 2})`.
- Systeemverwerking: `ToolPermissionManager.is_tool_allowed("copilot", "create_task")` controleert de allowlist; `ToolRiskClassifier.classify("create_task")` retourneert `medium`; omdat het geen HIGH-risk tool is, wordt geen HITL-ticket geëist; de aanroep wordt doorgeschoven naar `BusinessToolRegistry`.
- Succesrespons: `{"success": true, "data": {"id": "...", "title": "...", "status": "todo", ...}}`.
- Foutrespons: `ToolExecutionException` met detail "Permission denied: Agent 'copilot' is not authorized to use tool 'create_task'" als de tool niet in het profiel staat.
- Uitzonderingen: Als `create_task` niet expliciet in `tool_risk_levels` staat, valt het terug op `default_risk_level: high` en wordt onterecht HITL vereist.

---

## H. Definition of Done

- [x] Configuratie is aangepast.
- [x] Bestaande tests blijven groen.
- [x] Nieuwe unit- en integratietests voor `create_task`/`list_tasks` zijn groen.
- [x] Trainingssamenvatting is aanwezig.
