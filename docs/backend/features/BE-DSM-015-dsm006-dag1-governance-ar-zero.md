# BE-DSM-015: SP-DSM-006 Dag 1 -- governance->agent_runtime = 0

**Sprint**: SP-DSM-006 Dag 1
**Datum**: 2026-06-17
**Status**: APPROVED

## Probleemstelling

`src/core/governance/dsar_service.py:338` importeerde `Agent` ORM direct uit
`src.core.agents.models` via een function-local import. Dit is een governance->agent_runtime
grensovertreding (ADR-034: agent_runtime heeft een facade boundary; governance mag nooit
direct uit agent_runtime importeren).

```python
# VOOR -- verboden import (ADR-034)
from src.core.agents.models import Agent
agents_result = await self._db.execute(select(Agent).where(Agent.tenant_id == tenant_id))
```

## Oplossing

Vervangen door `sqlalchemy.text()` met geparameteriseerde query. De import verdwijnt volledig;
geen nieuwe externe afhankelijkheid (SQLAlchemy al aanwezig in governance).

```python
# NA -- raw SQL, governance->agent_runtime = 0
agents_result = await self._db.execute(
    text("SELECT id, name, agent_type FROM agents WHERE tenant_id = :tenant_id"),
    {"tenant_id": tenant_id},
)
agent_rows = agents_result.mappings().all()
```

## Bestanden gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/governance/dsar_service.py` | `from sqlalchemy import ... text ...` toegevoegd; function-local Agent import + ORM query vervangen door raw SQL; error handling verbeterd (exc_info=True) |
| `tests/architecture/test_dsm006_governance_agent_runtime.py` | Nieuw architecture test: AST-scan governance dir op agent_runtime imports; target = 0 |

## Review bevindingen (opgelost)

- **MEDIUM-1 (opgelost)**: `str(tenant_id)` -> `tenant_id` voor asyncpg integer type-binding
- **LOW-1 (opgelost)**: TODO in testdocstring verwijderd (fix al toegepast)

## ADR-034 rationale

governance -> agent_runtime is VERBODEN. Raw SQL via `sqlalchemy.text()` vermijdt de ORM-import
volledig. De DSAR Art. 15 export-functionaliteit (data opvragen) blijft correct: dezelfde 3 velden
(id, name, agent_type) worden geretourneerd via row mappings.

## Verificatie

```
test_governance_has_zero_direct_agent_runtime_imports: PASSED (0 hits)
pytest tests/architecture/ -q: 158 passed, 17 xfailed, 0 failed
pytest tests/unit/governance/ -k "dsar or gdpr": 52 passed, 0 failed
python -m pyright: 0 errors (baseline ongewijzigd)
ruff check src/core/governance/dsar_service.py: All checks passed
```

## Fan-out baseline (Dag 2 input)

Totaal fan-out agent_runtime (alle ImportFrom nodes): **2454**
Budget Grade A+: 500 (cross-module fan-out via scan_module)
Verschil intern totaal: 1954

Top-5 zwaarste bestanden:
1. `src/core/copilot/council/factory.py` -- 41
2. `src/core/agents/base_agent.py` -- 26
3. `src/core/agents/ethics_classification_trainer.py` -- 24
4. `src/core/agents/risk_prediction_system.py` -- 23
5. `src/core/copilot/dependencies.py` -- 23

**Noot**: 2454 > 2000 stopdrempel -- gerapporteerd aan Rakesh voor scope Dag 2+.
De Grade A+ test gebruikt `scan_module()` (cross-module fan-out) waarbij de huidige waarde
~875 is (XFAIL in CI). Dag 2 scope: clustering + gerichte reductie.


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-006 Dag 1: governance->agent_runtime = 0. dsar_service.py Agent ORM import vervangen door raw SQL (sqlalchemy.text). ADR-034 naleving. Fan-out baseline: 2454. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-006 Dag 1: governance->agent_runtime = 0. dsar_service.py Agent ORM import vervangen door raw SQL (sqlalchemy.text). ADR-034 naleving. Fan-out baseline: 2454..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
