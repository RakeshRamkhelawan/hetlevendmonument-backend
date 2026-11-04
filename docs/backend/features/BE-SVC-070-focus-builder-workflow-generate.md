# BE-SVC-070: Focus Builder Workflow Generation via complete_json()

## Samenvatting

Vervanging van de Focus Builder AI-generatie pipeline door een end-to-end geteste, deterministische keten die `LLMClient.complete_json()` gebruikt met `ReactFlowGraph` als JSON-schema. Dit elimineert handmatige JSON-parsing en maakt gestructureerde output betrouwbaar.

## Sprint

SP-G04 Dag 1

## Datum

2026-05-30

## Componenten

| Component | Pad | Wijziging |
|-----------|-----|-----------|
| LLMService | `src/core/llm/llm_service.py` | Nieuwe methode `complete_json()` |
| LLMProviderProtocol | `src/core/llm/llm_client.py` | Uitbreiding met `complete_json()` |
| AgenticFlowService | `src/domains/flows/agentic_service.py` | Refactor `generate_flow_from_prompt()` |
| FocusBuilder Router | `src/core/api/v1/focus_builder/router.py` | Response wrapper aanpassing |
| Tests | `tests/unit/test_sp_g04_focus_builder_workflow_generate.py` | 14 TDD-tests |

## Architectuur

### Before
```
User Prompt
    -> AgenticFlowService.generate_flow_from_prompt()
        -> plan_automation_from_prompt() [LLMService.generate_response() + handmatige JSON parsing]
        -> steps_to_reactflow() [deterministische mapping]
        -> fallback: _legacy_generate_flow()
    -> Endpoint retourneert {"graph": {...}, "prompt": ...}
```

### After
```
User Prompt
    -> AgenticFlowService.generate_flow_from_prompt()
        -> pack matching (bestaand, ongewijzigd)
        -> LLMService.complete_json(messages, schema=ReactFlowGraph)
            -> provider.complete_json() [native JSON-mode]
        -> ReactFlowGraph(**json.loads(content))
    -> Endpoint retourneert {"success": true, "data": {"react_flow_graph": {...}}}
```

## API Contract

### Request
```http
POST /api/v1/focus-builder/ai/generate
Content-Type: application/json

{"prompt": "Send an email when a form is submitted"}
```

### Response (success)
```json
{
  "success": true,
  "data": {
    "react_flow_graph": {
      "nodes": [
        {"id": "trigger_1", "type": "trigger", "position": {"x": 250, "y": 200}, "data": {"label": "Start"}}
      ],
      "edges": []
    }
  }
}
```

### Response (error)
```json
{
  "success": false,
  "error": {
    "code": "LLM_GENERATION_FAILED",
    "message": "Provider unavailable"
  }
}
```

## Tenant Isolatie

- `tenant_id` wordt uit de JWT claim gehaald via `get_current_user_dependency()`
- `tenant_id` wordt expliciet in het LLM prompt context opgenomen (`tenant_id: {id}. Request: ...`)
- Geen `tenant_id` in request body

## Governance

- Endpoint blijft onderworpen aan `require_council_approval()` (ADR-031)
- Council verdicts: APPROVED -> doorgaan, BLOCKED/HITL_REQUIRED -> 403

## Testdekking

| Test | Scope | Aantal |
|------|-------|--------|
| Schema validatie | Unit | 3 |
| LLMService.complete_json() | Unit | 3 |
| AgenticFlowService.generate_flow_from_prompt() | Unit | 4 |
| Endpoint wrapper + governance | Unit | 4 |
| **Totaal** | | **14** |

### Regressiecheck
- SP-D01 tests: 19/19 PASS
- LLM override tests: 10/10 PASS
- Council gate tests: 6/6 PASS
- Copilot + LLM + services: 484/484 PASS

## Trainingssamenvatting

| Veld | Waarde |
|------|--------|
| **Actor** | API Client / Frontend (Focus Builder) |
| **Voorwaarde** | User prompt aanwezig; Council governance akkoord (APPROVED) |
| **Actie (request)** | `POST /api/v1/focus-builder/ai/generate` |
| **Systeemverwerking** | Council deliberatie -> LLM native JSON mode aanroep met `ReactFlowGraph` schema -> Data mapping naar response envelope |
| **Succesrespons** | HTTP 200 met gestructureerde graph (`nodes`, `edges`) |
| **Foutrespons** | 403 (Council veto of HITL vereist), 500 (LLM provider error) |
| **Uitzonderingen** | Bij lege prompt retourneert de AI een minimaal start-node schema |

## Afhankelijkheden

- SP-D01 (LLM complete_json fix): CLOSED, GO
- `ReactFlowGraph` Pydantic schema (bestaand in `src/domains/flows/models.py`)

## Wijzigingen buiten scope

- `learning_mixin.py`: pre-existing SyntaxError gefixt (`if TYPE_CHECKING: ... except ImportError:` -> `try/except`)
- `router.py`: pre-existing `NameError: name 'Response' is not defined` gefixt (import toegevoegd)
