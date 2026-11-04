# BE-DSM-017 -- SP-DSM-006 Dag 3: Scanner fix + 365 relatieve imports gesaneerd

**Sprint**: SP-DSM-006 Dag 3  
**Commit**: 5e33f023  
**Datum**: 2026-06-18  
**Status**: APPROVED

---

## Samenvatting

Twee structurele verbeteringen aan de DSM import-linter infrastructuur:

1. **Scanner blind spot gefixd** (`scripts/dsm_full_analysis.py`): De scanner negeerde alle
   relatieve imports (`node.level > 0`). Via CPython `_resolve_name` algoritme worden
   relatieve imports nu omgezet naar absolute module-namen en meegeteld. Zichtbare
   fan-out agent_runtime: 800 -> 1018 (+218 hidden cross-module imports nu zichtbaar).

2. **365 relatieve imports gesaneerd** in `src/core/agents/generated/` (73 bestanden):
   Alle 5 relatieve import-patronen zijn vervangen door absolute imports (ADR-034).
   Na sanering: fan-out 1018 -> 946 (-72 llm-imports intern via llm_types shim).

3. **TID252 CI gate geactiveerd** (`pyproject.toml`): Ruff `ban-relative-imports =
   "parents"` bewaakt voortaan dat geen nieuwe relatieve parent-imports in `generated/`
   binnensluipen.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `scripts/dsm_full_analysis.py` | +2 helpers (`_file_to_module`, `_resolve_relative_import`) + scan_module loop |
| `src/core/agents/generated/*.py` (73 files) | 5 relatieve imports per bestand -> absoluut |
| `src/core/services/stripe_service.py` | `from ..config` -> `from src.core.config` |
| `src/core/services/usage_service.py` | `from ..models` -> `from src.core.models` |
| `src/core/agents/agent_factory.py` | Generator template: `from core.llm` -> `from src.core.agents.llm_types` |
| `pyproject.toml` | TID252 toegevoegd aan select + flake8-tidy-imports sectie |
| `tests/architecture/test_dsm006_generated_agents_no_relative_llm.py` | Nieuw (GROEN) |
| `tests/architecture/test_dsm006_scanner_no_hidden_relative.py` | Nieuw (GROEN) |

---

## Technische details

### Scanner fix (_file_to_module + _resolve_relative_import)

CPython `_resolve_name` algoritme:
- Bestandspad -> module-naam: `src.core.agents.generated.foo`
- Package = module zonder laatste segment: `src.core.agents.generated`
- Voor level=4: 3x rpartition(".") omhoog -> base = `src`
- Resolved: `src.core.llm.agent_model_matcher`

### 5 vervangen patronen (per generated agent)

| Van | Naar |
|-----|------|
| `from ....core.llm.agent_model_matcher import ...` | `from src.core.agents.llm_types import ...` (shim = intern) |
| `from ....core.shared.interfaces import ...` | `from src.core.shared.interfaces import ...` |
| `from ....core.shared.llm_client import ...` | `from src.core.shared.llm_client import ...` |
| `from ....core.agents.base_agent import ...` | `from src.core.agents.base_agent import ...` |
| `from ....core.agents.mixins.critic_mixin import ...` | `from src.core.agents.mixins.critic_mixin import ...` |

### TID252 backlog (13 bestanden met TODO(SP-DSM-007))

23 violations buiten generated/ zijn intern of cross-module. Ze staan in per-file-ignores
en worden in SP-DSM-007 gemigreerd. generated/ heeft geen per-file-ignore: gate is actief.

---

## Meetresultaten

| Metriek | Voor Dag 3 | Na Dag 3 |
|---------|-----------|----------|
| Scanner-zichtbare fan-out | 800 | 946 |
| Werkelijke fan-out (incl. hidden) | 1018 | 946 |
| Relatieve imports in generated/ | 365 | 0 |
| Architecture tests | 158 passed, 17 xfailed | 160 passed, 17 xfailed |
| TID252 violations generated/ | 949 | 0 |
| Pyright errors | 0 | 0 |

---

## ADR-naleving

- **ADR-034**: agent_runtime facade -- generated agents importeren nu uitsluitend absoluut
- **ADR-033**: import-linter contracts -- scanner correct, TID252 gate actief


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-006 Dag 3: Scanner blind spot gefixd (\_file_to_module + CPython \_resolve_name). 365 relatieve imports in generated/ gesaneerd. fan-out 1018->946 (-72 llm intern). TID252 CI gate actief. 160 architecture tests. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-006 Dag 3: Scanner blind spot gefixd (\_file_to_module + CPython \_resolve_name). 365 relatieve imports in generated/ gesaneerd. fan-out 1018->946 (-72 llm intern). TID252 CI gate actief. 160 architecture tests..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
