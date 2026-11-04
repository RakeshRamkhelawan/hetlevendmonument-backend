# BE-SVC-003: Focus Builder AI Generate LLM Integration

**ID:** BE-SVC-003  
**Sprint:** SP-D01  
**Datum:** 2026-05-28  
**Status:** APPROVED  
**Eigenaar:** Rakesh Ramkhelawan  

---

## Samenvatting

Vervang template-based workflow-generatie in de Focus Builder `POST /focus-builder/ai/generate` endpoint door een echte LLM-aanroep via `AgenticFlowService`.  
Voorheen retourneerde het endpoint altijd hetzelfde 2-node template ongeacht de prompt.  
Na deze fix wordt een volledige LLM pipeline gebruikt met planning, domain pack matching, en repair loops.

---

## Wijzigingen

### Bestanden gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/focus_builder/router.py` | `generate_flow_ai()` endpoint delegeert nu naar `AgenticFlowService.generate_flow_from_prompt()` |

---

## Flow

```
User -> POST /focus-builder/ai/generate
  -> Governance gate (AgentCouncil deliberation)
  -> AgenticFlowService.generate_flow_from_prompt()
    -> Phase 0: Domain Pack Matching (tenant-scoped)
    -> Phase 1: Strategic Planning (LLM JSON-mode)
    -> Phase 2: Drafting (Python mapping naar ReactFlow)
    -> Repair Loop (bij invalid JSON / schema mismatch)
  <- Return {"graph": {...nodes, edges...}, "prompt": prompt}
```

---

## Endpoint

| Methode | Pad | Rate Limit |
|---------|-----|------------|
| `POST` | `/api/v1/focus-builder/ai/generate` | 3/minute |

### Request body

```json
{"prompt": "string"}
```

### Response body

```json
{
  "graph": {
    "nodes": [...],
    "edges": [...]
  },
  "prompt": "string"
}
```

### Error responses

| Status | Code | Oorzaak |
|--------|------|---------|
| 400 | VALIDATION_ERROR | Prompt ontbreekt |
| 500 | GENERATION_ERROR | LLM generatie mislukt |

---

## Governance

- `require_council_approval()` wordt aangeroepen voor LLM-generatie (ADR-031)
- `action_type`: `"focus_builder.ai_generate"`

---

## Tests

```bash
pytest tests/unit/test_sp_d01_llm_fix.py::TestFocusBuilderUsesLLM -v
# 3 passed

pytest tests/unit/ai_act_governance/test_gap_fixes.py -k "focus_builder_generate" -v
# 2 passed
```

---

## Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Eindgebruiker via Focus Builder UI |
| Voorwaarde | Geauthenticeerd, tenant geconfigureerd, LLM provider beschikbaar |
| Actie | Gebruiker typt natuurlijke-taal prompt en klikt "Genereer" |
| Systeemreactie | AgenticFlowService vertaalt prompt naar ReactFlow graph via LLM |
| Succesrespons | `{"graph": {"nodes": [...], "edges": [...]}, "prompt": "..."}` |
| Foutrespons | HTTP 400 (leeg prompt) of HTTP 500 (LLM fout) |
| Uitzonderingen | Domain pack template match bypasses LLM generation indien exacte match |
