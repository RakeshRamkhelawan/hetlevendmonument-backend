# BE-AGT-024: ShadowCEO critique-score risicosignaal (Check 6)

**Sprint:** SP-AGT-008 Dag 1  
**Status:** APPROVED  
**Datum:** 2026-06-28

---

## Samenvatting

`ShadowCEO.review_task()` heeft nu een zesde risicocheck: de gemiddelde critique-score
van de voorgestelde agent (via `CritiqueStore.get_by_agent()`) wordt opgehaald en, als
de score onder de drempel van 0.35 valt, toegevoegd als HIGH-risicofactor.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/als/enterprise/shadow/shadow_ceo.py` | `_CRITIQUE_RISK_THRESHOLD = 0.35`, Check 6 in `review_task()`, `_assess_critique_risk()` methode |
| `.importlinter` | Cat B whitelist: `shadow_ceo -> critique_store` |

---

## Ontwerpbeslissingen

- **Pull-interface**: `_assess_critique_risk()` roept synchroon `store.get_by_agent()` aan
  in `review_task()`. Geen event-bus — vermijdt ordering-complexiteit (ADR-016 compliant).
- **Drempel 0.35**: bewust lager dan de HITL-drempel van 0.40 in `CritiqueStore`.
  ShadowCEO waarschuwt eerder, voordat een HITL-ticket aangemaakt wordt.
- **Lazy import**: `get_critique_store()` wordt lazy geimporteerd in `_assess_critique_risk()`
  zodat de Cat B grens gerespecteerd wordt.
- **Foutafscherming**: alle exceptions worden geabsorbeerd; `review_task()` krijgt nooit
  een exception terug van Check 6.

---

## Tests

| Testbestand | Dekking |
|-------------|---------|
| `tests/unit/agents/test_shadow_ceo_critique_signal.py` | 6 tests: threshold-attribuut, veto bij lage score, geen veto bij hoge score, geen veto zonder data, store-aanroep, exception-absorptie |

Alle 6 tests GROEN.

---

## Trainingssamenvatting

**Actor:** ShadowCEO  
**Voorwaarde:** `review_task()` aangeroepen met een `proposed_agent`  
**Actie:** haal gemiddelde critique-score op via `CritiqueStore.get_by_agent(limit=10)`  
**Systeemreactie:** voeg `RiskLevel.HIGH` + reden toe als `avg_score < 0.35`  
**Succes:** veto-melding bevat `critique_score_low` reden  
**Fout:** geen data beschikbaar of store-exception -- `RiskLevel.NONE` teruggegeven  
**Uitzondering:** score precies op drempel (0.35) geeft geen veto
