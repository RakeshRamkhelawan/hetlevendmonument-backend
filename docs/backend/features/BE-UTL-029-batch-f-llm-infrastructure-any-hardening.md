---
id: BE-UTL-029
name: Batch F -- LLM/Infrastructure/Resilience Any Hardening
sprint: SP-ANY-F
date: 2026-05-31
status: APPROVED WITH MINOR GAPS
commit: 672fc5a8
---

# BE-UTL-029 -- Batch F LLM/Infrastructure/Resilience

## Samenvatting

Laatste batch van Any Fase 2. 15 bestanden aangepakt; 11 service/domain-bestanden
hadden al TODOs op correcte regel (0 echte violations). Netto resultaat: -126
violations, cumulatief -305 (-60.2%) t.o.v. startpunt 507.

## Nieuwe TypedDicts

| TypedDict | Bestand | Fields |
|-----------|---------|--------|
| `_StatsDict` | llm/fallback_chain.py | total_calls: int, successful_calls: int, fallback_count: int, tier_usage: dict[str,int] |

## Type fixes

| Bestand | Wijziging |
|---------|-----------|
| fallback_chain.py | `_stats: dict[str,Any]` -> `_StatsDict`; `get_stats()` -> `dict[str,object]` |
| retry_policy.py | `circuit_breaker: Any\|None` -> `CircuitBreaker\|None`; module-level import toegevoegd |
| pubsub_manager.py | `listening_task: asyncio.Task[Any]\|None` -> `asyncio.Task[None]\|None` |
| ollama_provider.py | `parsed_function_calls` -> `list[dict[str,object]]`; UP035 fixed |
| gemini_provider.py | `function_calls` -> `list[dict[str,object]]`; UP035 fixed |
| mock_provider.py | `_json_response` -> `dict[str,str\|float]`; UP035 fixed |
| llm_service.py | `tools: list[Any]` behouden + NOTE-comment (Gemini callable vs JSON-schema dicts) |

## Gate 2 beslissingen (2 rondes)

- **`_providers: dict[str, object]`** NIET gebruikt — `.chat` en `.aio` methoden op
  provider-instances zouden Pyright-errors geven; terug naar `dict[str, Any]` met TODO
- **`_StatsDict` TypedDict** i.p.v. `dict[str,object]` voor `_stats` — `+= 1` sites
  vereisen concrete int annotatie, niet `object`
- **`tools: list[Any]`** behouden met NOTE — Gemini passeert callables,
  Ollama/OpenAI passeert dict schemas; twee distincte shapes
- **`circuit_breaker: CircuitBreaker | None`** — geen circular import (grep bevestigd);
  module-level import safe

## Trainingssamenvatting

### Flow: TypedDict voor intern bijgehouden stats-dict

| Stap | Detail |
|------|--------|
| **Voorwaarde** | `self._stats: dict[str,Any]` met `+= 1` operaties op values |
| **Actie** | Definieer `_StatsDict(TypedDict)` met exacte veld-types; verander annotatie |
| **Systeemverwerking** | Pyright valideert `+= 1` tegen `int` veld-type -- type-safe |
| **Foutrespons** | `dict[str,object]` breekt `+= 1` (`object` ondersteunt `+=` niet) |
| **Uitzondering** | Als return-dict EXTRA keys toevoegt (heterogeen): return type `dict[str,object]` |

### Flow: Polymorfische provider-instanties bewust `Any` houden

| Stap | Detail |
|------|--------|
| **Voorwaarde** | `dict[str, Any]` voor container van polymorfische SDK-objecten |
| **Actie** | Poging `dict[str, object]` -- Pyright error op methode-aanroepen |
| **Beslissing** | Behoud `dict[str,Any]` + TODO -- `object` breekt `.chat`, `.aio` attrs |
| **Les** | `object` is correct voor WAARDEN die als JSON worden doorgegeven, NIET voor SDK-objecten met methoden |

## TDD

- `tests/unit/test_batch_f_type_hardening.py`: 7 tests, 7/7 PASS

## Kwaliteitsresultaten

- `ruff check` alle bestanden: 0 errors (incl. UP035 fixes)
- Gate 2: 2 rondes, APPROVED na correcties
- Scan: 328 -> 202 violations (-126, -38.4%)
- Cumulatief Fase 2: 507 -> 202 (-305, -60.2%)


## Trainingssamenvatting

### Flow 1: Type-hardening toepassen op LLM-infrastructure

- Actor: Ontwikkelaar of type-hardening sprint-agent
- Voorwaarde: Any-types aanwezig in LLM-providers, fallback-chains en configuratie-objecten
- Actie: Concrete TypedDicts en Protocol-klassen vervangen bare Any-annotaties
- Systeemverwerking: mypy en pyright controleren de nieuwe annotaties; ruff UP035 waarschuwingen worden geelimineerd
- Succesrespons: 0 nieuwe mypy-errors; ruff All checks passed; bestaande tests groen
- Foutrespons: Als een type-annotatie incorrect is: mypy-error die de sprint blokkeert tot fix
- Uitzonderingen: Sommige LLM-responses zijn inherent polymorf; Any met TODO(TYPE)-comment is toegestaan als tussenoplossing
