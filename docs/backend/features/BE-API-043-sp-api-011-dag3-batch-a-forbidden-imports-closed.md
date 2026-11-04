# BE-API-043: SP-API-011 Dag 3 -- Batch A verboden imports gesloten (3 xfails -> 0)

## Status: APPROVED

## Sprint: SP-API-011 Dag 3

## Datum: 2026-06-27

---

## Samenvatting

Sluit de laatste 3 xfailed architecture tests door alle verboden imports uit de 3 Batch A
flat-file endpoints te redirecten naar ADR-033 facade bestanden.
Arch-suite eindigt op 294 passed, 0 failed, 0 xfailed (was 291/0/3 voor dag 3).

---

## Probleemstelling

`tests/architecture/test_flat_file_batch_a_gaps.py` bevatte 3 `xfail(strict=True)` tests:
- `test_agent_endpoints_has_zero_forbidden_imports` -- 9 verboden imports in `agent_endpoints.py`
- `test_admin_learning_endpoints_has_zero_forbidden_imports` -- 5 verboden imports in `admin_learning_endpoints.py`
- `test_assistant_endpoints_has_zero_forbidden_imports` -- 5 verboden imports in `assistant_endpoints.py`

Blocker was dat een directe `*_dependencies.py` facade nog ontbrak, en dat `agent_registry`
niet op module-import-niveau geladen mocht worden (bewaakd door `test_agent_endpoints_imports_without_agent_registry`).

---

## Implementatie

### Nieuwe facade bestanden (ADR-033 flat-file patroon)

**`src/core/api/agent_endpoints_db_dependencies.py`**
- Herexporteert alleen `get_db` uit `src.core.database.database`
- Veilig voor module-level import (laadt agent_registry NIET transitief)

**`src/core/api/agent_endpoints_dependencies.py`**
- Herexporteert `AgentRegistry`, `AgentRegistryRepository`, `RegisteredAgent`
- Wordt alleen gebruikt in `if TYPE_CHECKING:` blokken en function bodies
- Nooit op module-level in `agent_endpoints.py` geimporteerd

**`src/core/api/admin_learning_endpoints_dependencies.py`**
- Herexporteert `get_db`, `AuditLog`, `consent_read_limit`, `consent_update_limit`,
  `LearningBudgetService`, `LearningGDPRService`

**`src/core/api/assistant_endpoints_dependencies.py`**
- Herexporteert `ConversationMemory`, `UltimateExecutionResult`, `UltimateCVAAgent`,
  `create_ultimate_cva_agent`, `get_redis_client`

### Gewijzigde flat files

**`src/core/api/agent_endpoints.py`**
- Line 33: `get_db` nu via `agent_endpoints_db_dependencies` (module-level, veilig)
- Lines 38-40 (TYPE_CHECKING): 3 imports nu via `agent_endpoints_dependencies`
- Lines 51-52 (get_agent_registry_dependency body): 2 imports via `agent_endpoints_dependencies`
- Lines 945, 986-987 (handler bodies): RegisteredAgent + AgentRegistryRepository via facade

**`src/core/api/admin_learning_endpoints.py`**
- Alle 5 verboden module-level imports vervangen door `admin_learning_endpoints_dependencies`

**`src/core/api/assistant_endpoints.py`**
- Lines 14-16: 3 module-level imports via `assistant_endpoints_dependencies`
- Line 75: lazy import via `assistant_endpoints_dependencies`
- Line 140: try-block compat-alias via `assistant_endpoints_dependencies`

### Arch-test wijzigingen

**`tests/architecture/test_flat_file_batch_a_gaps.py`**
- 3 `xfail(strict=True)` markers verwijderd (agent, admin_learning, assistant)
- `import pytest` verwijderd (niet meer nodig)

### Finder script

**`scripts/dsm_api_violation_finder.py`**
- `is_api_layer_file()`: extra exemptie toegevoegd voor `*_dependencies.py` bestanden
- Reden: `*_dependencies.py` zijn de ADR-033 facade bestanden zelf; ze zijn geen schending

---

## Kritieke ontwerpbeslissing: split facade

`agent_endpoints.py` heeft een bestaande passing test:
`test_agent_endpoints_imports_without_agent_registry` -- bewaakt dat `src.core.agents.agent_registry`
niet op module-import-niveau geladen wordt.

Daarom zijn 2 aparte facades aangemaakt:
- `agent_endpoints_db_dependencies.py` -- alleen `get_db`, veilig voor module-level import
- `agent_endpoints_dependencies.py` -- agent domain types, ALLEEN in TYPE_CHECKING of function body

`agent_endpoints_dependencies.py` wordt NOOIT op module-level geimporteerd in `agent_endpoints.py`.

---

## Verificatie

```
tests/architecture/ -- 294 passed, 0 failed, 0 xfailed
python -m pyright   -- 0 errors, 57 warnings
tests/unit/api/     -- 177 passed (geen regressies)
tests/unit/test_agent_endpoints.py -- 20 passed, 3 xfailed (pre-existing)
```

### Pre-existing failures (niet veroorzaakt door dag 3)

`tests/unit/test_assistant_endpoints.py::TestAssistantEndpoints::test_ask_assistant_success`
`tests/unit/test_assistant_endpoints.py::TestAssistantEndpoints::test_ask_assistant_error`

- Tests verwachten `status_code=500` maar de echte LLM (DeepSeek) wordt aangeroepen en geeft 200
- Faalde al voor dag 3; geen mock op `create_ultimate_cva_agent` in de test setup
- Scope: pre-existing, niet veroorzaakt door import-redirect

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/agent_endpoints_db_dependencies.py` | Nieuw -- get_db facade |
| `src/core/api/agent_endpoints_dependencies.py` | Nieuw -- agent domain facade |
| `src/core/api/admin_learning_endpoints_dependencies.py` | Nieuw -- admin learning facade |
| `src/core/api/assistant_endpoints_dependencies.py` | Nieuw -- assistant facade |
| `src/core/api/agent_endpoints.py` | Verboden imports -> facades |
| `src/core/api/admin_learning_endpoints.py` | Verboden imports -> facade |
| `src/core/api/assistant_endpoints.py` | Verboden imports -> facade |
| `tests/architecture/test_flat_file_batch_a_gaps.py` | 3 xfail markers verwijderd |
| `scripts/dsm_api_violation_finder.py` | *_dependencies.py exempt toegevoegd |


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-API-011 Dag 3 (CLOSED): 3 xfails gesloten. 4 nieuwe *_dependencies.py facades: agent_endpoints_db (get_db), agent_endpoints (AgentRegistry+Repo+RegisteredAgent), admin_learning (get_db+AuditLog+rates+LearningBudget+GDPR), assistant (UltimateCVA+Memory+redis). agent/admin_learning/assistant forbidden imports -> facades. *_dependencies.py exempt in finder. Arch: 294 passed, 0 xfailed (was 3). pyright 0 errors. SP-API-011 CLOSED. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-API-011 Dag 3 (CLOSED): 3 xfails gesloten. 4 nieuwe *_dependencies.py facades: agent_endpoints_db (get_db), agent_endpoints (AgentRegistry+Repo+RegisteredAgent), admin_learning (get_db+AuditLog+rates+LearningBudget+GDPR), assistant (UltimateCVA+Memory+redis). agent/admin_learning/assistant forbidden imports -> facades. *_dependencies.py exempt in finder. Arch: 294 passed, 0 xfailed (was 3). pyright 0 errors. SP-API-011 CLOSED..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
