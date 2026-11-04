# Backend Feature Specification

## Metadata

- Feature ID: BE-GOV-003
- Feature naam: RC-001 -- Council gate op agent execute/collaborate routes
- Status: APPROVED
- Auteur: SP-GOV-002 Dag 1
- Reviewer: zie docs/backend/review/review-BE-GOV-003.md
- Datum: 2026-06-22
- Gerelateerde user story / ticket: AGENT-CVA-COUNCIL-AUDIT-2026-06-20 RC-001
- Gerelateerde router / module: src/core/api/v1/agents/agent_execution_router.py, agent_management_router.py, dependencies.py
- Gerelateerde database tabellen: council_decisions
- Versie: 1.0

---

## Doel en scope

### Doel

RC-001 audit bevinding gesloten: de agent execute en collaborate routes hadden geen council
governance gate. Elke agent-uitvoering kon direct de LLM bereiken zonder AI Act Art. 14
deliberatie.

### Scope

- `dependencies.py`: `get_council_dependency()` facade functie toegevoegd (lazy import van `build_council`)
- `agent_execution_router.py`: 3 execute handlers (`/execute`, `/agent/execute/{id}`, `/execute/{id}`) uitgebreid met council inject + `require_council_approval` (action_type: `agent.execute`)
- `agent_management_router.py`: `/collaborate` handler uitgebreid met council inject + `require_council_approval` (action_type: `agent.collaborate`)

---

## Architectuur

### Patroon

ADR-033 compliant: `require_council_approval` wordt via function-body lazy import aangeroepen
(niet module-level), zodat de router boundary niet wordt geschonden. Council wordt geinjecteerd
via `Depends(get_council_dependency)` uit de `dependencies.py` facade.

### Council parameters

```python
await require_council_approval(
    council=council,
    tenant_id=current_user.tenant_id,
    user_id=current_user.id,
    action_type="agent.execute",          # of "agent.collaborate"
    action_params={"agent_id": agent_id}, # of {"agent_ids": [...]}
    reasoning=f"Execute agent {agent_id}",
)
```

### Foutafhandeling

- Council blokkeert: HTTPException(403) met `GOVERNANCE_BLOCKED` code
- Council onbereikbaar: HTTPException(500) met `COUNCIL_UNAVAILABLE` code (fail-secure)

---

## Tests

| Test | Bestand | Type |
|------|---------|------|
| `test_execute_router_calls_require_council_approval` | test_agent_execution_council_gate.py | Architecture |
| `test_management_router_calls_require_council_approval` | test_agent_execution_council_gate.py | Architecture |
| `test_execute_primary_council_block_returns_403` | test_agent_execution_council_gate.py | Unhappy path |
| `test_collaborate_council_block_returns_403` | test_agent_execution_council_gate.py | Unhappy path |

---

## Definition of Done

- [x] Architecture tests GROEN (require_council_approval aanwezig in bron)
- [x] Unhappy path tests GROEN (403 bij blokkade)
- [x] Pyright 0 errors
- [x] Bestaande agent-endpoint regressietests GROEN (49 passed)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-GOV-002 Dag 1 RC-001: council gate op agent execute/collaborate routes. get_council_dependency facade in dependencies.py. require_council_approval in 3 execute + 1 collaborate handlers (function-body lazy import, ADR-033). 4 tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-GOV-002 Dag 1 RC-001: council gate op agent execute/collaborate routes. get_council_dependency facade in dependencies.py. require_council_approval in 3 execute + 1 collaborate handlers (function-body lazy import, ADR-033). 4 tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
