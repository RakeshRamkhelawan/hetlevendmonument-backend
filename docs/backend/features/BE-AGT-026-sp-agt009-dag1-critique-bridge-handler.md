# BE-AGT-026: TwinEventBridge CritiqueScoreLow learning handler

**Sprint:** SP-AGT-009 Dag 1
**Status:** APPROVED
**Datum:** 2026-06-28

---

## Samenvatting

Sluit ADR-025 gap #2 (Agent Learning event bridge) door een feature-flag-gated
`CritiqueScoreLow` handler toe te voegen aan `TwinEventBridge`. De handler
persisteert lage critique-scores als `LearningExperience`, exact hetzelfde
patroon als de bestaande `_on_intervention_suggested_learning` handler.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/learning/wiring/twin_event_bridge.py` | `CritiqueScoreLow` import, `_REDIS_EVENT_TYPE_MAP` entry, forwarding handler + learning handler, registratie in `start()` |
| `tests/unit/learning/test_twin_event_bridge_critique.py` | 4 unit tests: map-aanwezigheid, persist bij flag aan, skip bij flag uit, skip bij verkeerd event-type |

---

## Ontwerpbeslissingen

- **Geen nieuwe service**: `AgentLearningService` wordt niet aangemaakt. Het
  bridge-handler patroon is voldoende om gap #2 te sluiten.
- **Feature flag**: `"agent_learning"` wordt per-event gecontroleerd, identiek
  aan `_on_intervention_suggested_learning`. Runtime-togglebaar zonder bridge
  herstart.
- **Forwarding handler**: `_on_critique_score_low` stuurt het event door naar
  Redis Pub/Sub zodat de `_REDIS_EVENT_TYPE_MAP` entry actief wordt gebruikt.
- **Learning handler**: `_on_critique_score_low_learning` schrijft een
  `LearningExperience` rij met `success=False` (negatief leersignaal),
  `task_type="critique_signal"` en `confidence=event.score`.
- **Tenant isolatie**: RLS tenant context wordt gezet via
  `SET LOCAL app.current_tenant` voor de INSERT, gelijk aan het bestaande
  interventiepatroon.
- **Fail-safe**: alle DB-operaties lopen binnen `best_effort`; fouten breken
  de event bus niet.

---

## Tests

| Testbestand | Dekking |
|-------------|---------|
| `tests/unit/learning/test_twin_event_bridge_critique.py` | 4 tests: map-aanwezigheid, persist bij flag aan, skip bij flag uit, skip bij verkeerd event-type |

Alle 4 tests GROEN.

---

## Trainingssamenvatting

**Actor:** TwinEventBridge
**Voorwaarde:** `TwinEventBus` publiceert een `CritiqueScoreLow` event
**Actie:** forwarding handler stuurt naar Redis; learning handler persisteert
`LearningExperience` wanneer feature flag `"agent_learning"` aan staat
**Succes:** event doorgestuurd, DB-rij aangemaakt, geen exceptie
**Fout:** feature flag uit of ongeldig event-type -- handler returnt vroeg,
geen DB-call
**Uitzondering:** `tenant_id <= 0` of ontbrekende session_factory -- warning
geen crash
