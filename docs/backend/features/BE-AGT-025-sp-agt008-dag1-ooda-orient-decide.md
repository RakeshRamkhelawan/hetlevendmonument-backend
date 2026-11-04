# BE-AGT-025: OODALoopObserver Orient + Decide fasen

**Sprint:** SP-AGT-008 Dag 1  
**Status:** APPROVED  
**Datum:** 2026-06-28

---

## Samenvatting

`OODALoopObserver` implementeert de Orient- en Decide-fasen van de OODA-loop:

- **Orient**: publiceert `CritiqueScoreLow` event op `TwinEventBus` wanneer score < 0.35
- **Decide**: logt een interventieaanbeveling via `logger.info`

De Act-fase is post-MVP (ADR-025 par. 3.4).

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/learning/observers/ooda_loop_observer.py` | Orient + Decide fasen geimplementeerd (was stub) |
| `src/core/learning/events/twin_events.py` | `CritiqueScoreLow` dataclass toegevoegd |
| `.importlinter` | Cat B whitelist: `ooda_loop_observer -> event_bus`, `-> twin_events`, `-> best_effort` |

---

## Ontwerpbeslissingen

- **Drempel 0.35**: gelijk aan `ShadowCEO._CRITIQUE_RISK_THRESHOLD` -- dezelfde vroeg-waarschuwingsgrens.
- **`best_effort`**: orient-publicatie is fire-and-forget; het primaire pad wordt nooit geblokkeerd.
- **Module-level imports**: `get_twin_event_bus`, `CritiqueScoreLow` en `best_effort` zijn
  module-level geimporteerd (Cat B whitelist aanwezig). Patchbaar in tests.
- **`user_id` cast**: `TwinEvent.user_id` is `str`; `on_intervention_suggested` ontvangt `int`.
  Cast gebeurt expliciet: `str(user_id)`.
- **Type-narrowing**: `event_data: dict[str, object]` vereist `isinstance(raw_score, (int, float))`
  guard voor `float()` cast (pyright-compliant).

---

## Tests

| Testbestand | Dekking |
|-------------|---------|
| `tests/unit/learning/test_ooda_loop_orient_phase.py` | 5 tests: event publicatie bij lage score, geen publicatie boven drempel, tolerantie bij ontbrekende score, `CritiqueScoreLow` velden, decide-fase logging |

Alle 5 tests GROEN.

---

## Trainingssamenvatting

**Actor:** OODALoopObserver  
**Voorwaarde:** `on_intervention_suggested()` aangeroepen met `event_data` met `score` en `agent_name`  
**Actie (Orient):** als `score < 0.35`, publiceer `CritiqueScoreLow` op `TwinEventBus` via `best_effort`  
**Actie (Decide):** log `ooda_decide_intervention` met tenant_id, agent_name, score  
**Succes:** event gepubliceerd, log-entry aanwezig  
**Fout:** `score` ontbreekt of is geen getal -- vroeg return, geen publicatie  
**Uitzondering:** score precies op drempel (0.35) triggert geen Orient-fase
