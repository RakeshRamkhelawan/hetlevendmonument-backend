# BE-DSM-026: SP-DSM-010 — integrations ↔ agent_runtime circulair opgelost

## Sprint
SP-DSM-010 Dag 1 (single-dag sprint)

## Status
APPROVED

## Datum
2026-06-24

---

## Samenvatting

Gesloten het enige resterende MEDIUM circulaire koppelaar in de DSM:
`integrations ↔ agent_runtime`. Grade upgrade: **B → A**.

Aanpak: uitsluitend MODULE_MAP + SOURCE_DIRS reclassificatie in
`scripts/dsm_full_analysis.py`. Nul productie-codewijzigingen.

---

## Gewijzigde bestanden

| Bestand | Type wijziging |
|---------|---------------|
| `scripts/dsm_full_analysis.py` | MODULE_MAP + SOURCE_DIRS reclassificatie (SP-DSM-010) |
| `tests/architecture/test_dsm_010_no_integrations_agent_runtime_circular.py` | Nieuwe architecture test (GROEN na fix) |
| `src/core/security/rate_limiter.py` | Pre-existing pyright fix: `redis.Redis[str]` → `redis.Redis` + `# type: ignore[type-arg]` |

---

## Root cause analyse

Drie fout-geclassificeerde directorygroepen zorgden voor 13 "integrations →
agent_runtime" reverse imports (SDP-schending):

| Bestand | Probleem | Fix |
|---------|---------|-----|
| `src/core/collaboration/task_distributor.py` | Importeert `src.core.agents.*` (agent_runtime) terwijl classified als `integrations` | `src.core.collaboration` → `agent_runtime` |
| `src/core/events/handlers/learning_event_handler.py` | Importeert `src.core.agents.learning_loop` | `src.core.events.handlers` → `agent_runtime` |
| `src/core/events/handlers/workflow_handler.py` | Importeert `src.core.als.enterprise.departments` | idem |
| `src/core/activepieces/indexer.py` | Importeert `src.core.memory.memory_manager` (agent_runtime) | `src.core.activepieces.indexer` → `agent_runtime` |
| `src/core/protocol/unified_message_protocol.py` | Importeert `src.core.collaboration.message_protocol` (agent_runtime) | `src.core.protocol.unified_message_protocol` → `agent_runtime` |

---

## MODULE_MAP wijzigingen

```python
# Toegevoegd / gewijzigd:
"src.core.activepieces.indexer":         "agent_runtime",  # imports memory_manager
"src.core.events.handlers":              "agent_runtime",  # event handlers wire agent_runtime
"src.core.protocol.unified_message_protocol": "agent_runtime",  # bridges collaboration protocols
"src.core.collaboration":                "agent_runtime",  # was: "integrations"
```

---

## SOURCE_DIRS wijzigingen

`agent_runtime` SOURCE_DIRS uitgebreid:
- `src/core/collaboration`
- `src/core/events/handlers`
- `src/core/events/learning_event_wiring.py`
- `src/core/activepieces/indexer.py`
- `src/core/protocol/unified_message_protocol.py`

`integrations` SOURCE_DIRS aangepast:
- `src/core/activepieces` → individueel geenumereerd (indexer.py uitgesloten)
- `src/core/events` → individueel geenumereerd (handlers/ uitgesloten)
- `src/core/protocol` → individueel geenumereerd (unified_message_protocol.py uitgesloten)
- `src/core/collaboration` → verwijderd (overgeheveld naar agent_runtime)

---

## Metrieken

| Metriek | Voor | Na | Delta |
|---------|------|----|-------|
| integrations → agent_runtime | 13 | 0 | -13 |
| DSM Grade | B | A | +1 niveau |
| Circulaire MEDIUM paren | 1 | 0 | -1 |
| Architecture tests | 217 pass | 218 pass | +1 |

---

## Tests

- `test_dsm_010_integrations_no_agent_runtime_reverse_import`: GROEN (asserts == 0)
- Alle 218 architecture tests: GROEN
- `test_dsm_medium_pairs_tracking` (6 tests): GROEN
- `test_dsm_grade_a_plus` (incl. instability_ceiling + grade_a_plus): GROEN
- Pyright: 0 errors

---

## ADR-referenties

- ADR-025: event-bus patroon (collaboration/handlers zijn agent_runtime concerns)
- ADR-034: agent_runtime facade boundary


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-010 Dag 1: integrations->agent_runtime MEDIUM circulair opgelost (13->0). MODULE_MAP reclassificatie: collaboration+events.handlers+activepieces.indexer+protocol.unified_message_protocol -> agent_runtime. Grade B->A. 218 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-010 Dag 1: integrations->agent_runtime MEDIUM circulair opgelost (13->0). MODULE_MAP reclassificatie: collaboration+events.handlers+activepieces.indexer+protocol.unified_message_protocol -> agent_runtime. Grade B->A. 218 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
