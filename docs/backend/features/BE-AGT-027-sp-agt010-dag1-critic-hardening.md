# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-027
- Feature naam: SP-AGT-010 Dag 1: CriticAgent hardening -- YAML-config voor OutputSchemaValidator, judge-panel provider-diversiteit en configureerbare N
- Status: APPROVED
- Auteur: SP-AGT-010 Dag 1
- Reviewer: code-reviewer + quality-reviewer subagents (Gate 2)
- Datum: 2026-06-28

---

## Probleemstelling

SP-AGT-006 FA-briefs bevatten 3 open minors voor CriticAgent dag 1-items:

1. `OutputSchemaValidator` leest geen config uit YAML -- schemas zijn hardcoded in aanroepende code.
2. `_run_judge_panel` roept `self._get_llm_client()` aan voor elke judge -- alle judges gebruiken dezelfde provider, wat het doel van een panel ondergraaft.
3. `n_judges=3` is hardcoded als default parameter in `_judge_panel_critique` -- niet configureerbaar.

---

## Oplossing

### (A) `OutputSchemaValidator.create_for_capability(capability: str)`

Classmethod die `critic_agent.yaml` uitleest (elke aanroep, geen module-level cache) en een validator bouwt op basis van `capability_schemas[capability]`:

- `required_type`: string-naar-Python-type mapping via `_TYPE_MAP` (`"str"` -> `str`, `"dict"` -> `dict`, etc.)
- `required_fields`: lijst van verplichte velden
- `max_chars`: optionele tekenbeperking
- Onbekende capability: retourneert lege (no-constraint) validator

YAML-pad verankerd via `Path(__file__).resolve()` -- werkt ook in Gunicorn-workers (ADR-010).

### (B) `CriticAgent._get_judge_panel_size() -> int`

Leest `judge_panel_size` uit `critic_agent.yaml` (gecached in `__init__` als `self._judge_panel_size`).
Waarde wordt geclampt naar `[1, 5]`. Default bij ontbrekende of ongeldige config: 3.

`_judge_panel_critique` roept `self._get_judge_panel_size()` aan in plaats van de hardcoded `n_judges=3` default parameter.

### (C) Provider-diversiteit in `_run_judge_panel`

`_run_judge_panel` leest `judge_provider_types` uit YAML en roept `get_llm_provider(provider_type=...)` aan per judge (module-level import, patchbaar via `src.core.agents.critic_agent.get_llm_provider`).

Judge `i` gebruikt `providers[i % len(providers)]`. Fallback bij lege lijst: `"auto"`.

### YAML-wijzigingen (`config/agents/critic_agent.yaml`)

```yaml
judge_panel_size: 3
judge_provider_types:
  - deepseek
  - gemini
  - openai
```

### Pre-existing fix

`list[Any]` in `HeuristicScorer.score()` vervangen door `list[str]` -- elimineerde pyright-ruis die bij een volgend audit een regressie zou veroorzaken.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/critic_agent.py` | `_load_critic_agent_yaml()`, `_TYPE_MAP`, `create_for_capability`, `_get_judge_panel_size`, `_load_judge_panel_size`, provider-diversiteit in `_run_judge_panel`, `list[str]` fix |
| `config/agents/critic_agent.yaml` | `judge_panel_size: 3`, `judge_provider_types: [deepseek, gemini, openai]` |
| `tests/unit/agents/test_critic_agent_hardening_dag1.py` | 7 tests (4 YAML-reload + 1 provider-diversity + 2 panel-size) |

---

## Tests

| Test | Status |
|------|--------|
| `test_validator_for_capability_loads_from_yaml` | GROEN |
| `test_validator_for_capability_rejects_missing_field` | GROEN |
| `test_validator_for_unknown_capability_returns_default` | GROEN |
| `test_validator_for_capability_reads_yaml_each_call` | GROEN |
| `test_judge_panel_uses_different_providers` | GROEN |
| `test_judge_panel_size_read_from_config` | GROEN |
| `test_critic_agent_has_get_judge_panel_size_method` | GROEN |

Gerichte regressiecheck `tests/unit/agents/`: 432 passed, 0 failed.
Pyright: 0 errors (baseline gehandhaafd).

---

## ADR-compliance

- ADR-023 (CriticAgent): no violations -- bestaande critique_task flow ongewijzigd
- ADR-034 (agent_runtime boundary): `get_llm_provider` module-level import voldoet -- geen directe deep-imports
- CLAUDE.md: geen `datetime.now()`, geen emoji, geen tenant_id uit request body, ASCII-only


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-AGT-010 Dag 1: CriticAgent hardening -- YAML-config OutputSchemaValidator + judge provider-diversiteit + configureerbare N is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-AGT-010 Dag 1: CriticAgent hardening -- YAML-config OutputSchemaValidator + judge provider-diversiteit + configureerbare N.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
