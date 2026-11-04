# BE-AGT-028 -- EvalHarness + golden analyze_struggle() scenario's

## Build Summary

SP-AGT-009 Dag 2 levert een YAML-gestuurde evaluatieharnas (`EvalHarness`) voor
`PracticalTwinService.analyze_struggle()`. Het harnas laadt 5 "gouden" scenario's,
bouwt per scenario een `MockSuggestionProvider`, voert de analyse uit en rapporteert
welke scenario's slagen. Doel: regressietesten van struggle-detectie, consent-gate
en LLM-failover zonder echte LLM-calls.

---

## Backend Inventory

| ID         | Naam                  | Type     | Locatie                                                   | Gerelateerde flow |
| ---------- | --------------------- | -------- | --------------------------------------------------------- | ----------------- |
| BE-AGT-028 | EvalHarness           | Utility  | `src/core/learning/eval_harness.py`                       | ADR-025 §3        |
| BE-AGT-028 | EvalScenario          | Dataclass| `src/core/learning/eval_harness.py`                       | ADR-025 §3        |
| BE-AGT-028 | EvalResult            | Dataclass| `src/core/learning/eval_harness.py`                       | ADR-025 §3        |
| BE-AGT-028 | EvalReport            | Dataclass| `src/core/learning/eval_harness.py`                       | ADR-025 §3        |
| BE-AGT-028 | Golden scenario YAML  | Fixture  | `tests/unit/learning/fixtures/eval_scenarios.yaml`        | ADR-025 §3        |
| BE-AGT-028 | EvalHarness unit tests| Tests    | `tests/unit/learning/test_eval_harness.py`                | ADR-025 §3        |

---

## 1. EvalHarness

### 1.1 Doel
Voer herhaalbare, deterministische evaluaties uit op `PracticalTwinService.analyze_struggle()`
om te verifiëren dat:
- de weighted-struggle-score correct wordt berekend;
- interventies alleen worden gegeven boven de drempelwaarde (> 0.8);
- de `ai_interventions` consent-gate werkt (ADR-026);
- een falende LLM-provider niet crasht.

### 1.2 Functionele beschrijving
`EvalHarness` leest een YAML-bestand met scenario's. Per scenario wordt een
`PracticalTwinService` geinstantieerd met een `MockSuggestionProvider` die een
vooraf bepaalde response (of een fout) teruggeeft. Vervolgens wordt
`analyze_struggle()` aangeroepen. De werkelijke output wordt vergeleken met de
`expected` waarde in het scenario. Het resultaat is een `EvalReport` met per
scenario een `EvalResult` (passed/failed + diffs).

### 1.3 Technische beschrijving
- Bestand: `src/core/learning/eval_harness.py`
- Klassen: `EvalHarness`, `EvalScenario`, `EvalResult`, `EvalReport`
- Afhankelijkheden:
  - `PyYAML` voor `yaml.safe_load`
  - `PracticalTwinService` en `WeightedStruggleScore`
  - `MockSuggestionProvider`
  - `UserBehaviorObserver` (als `MagicMock(spec=...)`, niet als echte instantie)
- De default observer is een `MagicMock(spec=UserBehaviorObserver)` omdat
  `analyze_struggle()` de observer niet aanroept en de echte constructor
  verplichte afhankelijkheden heeft.

### 1.4 Request-specificatie (Python API)

```python
harness = EvalHarness(
    scenarios_path=Path("tests/unit/learning/fixtures/eval_scenarios.yaml"),
    observer=None,        # optional override
    cost_tracker=None,    # optional override
    event_bus=None,       # optional override
)
report: EvalReport = await harness.run()
```

### 1.5 Response-specificatie

`EvalReport` velden:
- `results`: list[`EvalResult`]
- `passed`: int
- `failed`: int
- `total`: int

`EvalResult` velden:
- `scenario_id`: str
- `passed`: bool
- `actual`: dict[str, Any]
- `expected`: dict[str, Any]
- `errors`: list[str]

### 1.6 Validaties en constraints
- Het scenario-bestand moet bestaan en binnen de project-root liggen.
- Het YAML-bestand moet een top-level `scenarios:` sleutel bevatten.
- `score`-vergelijking gebruikt een tolerantie van `0.001`.
- Scenario's met `raise_error: true` gebruiken een `MockSuggestionProvider` die
  een `RuntimeError` gooit.

### 1.7 Business rules
- Een scenario slaagt alleen als alle opgegeven `expected` sleutels exact
  (met float-tolerantie) overeenkomen met de werkelijke output.
- De consent-gate in `analyze_struggle()` bepaalt dat `ai_interventions=False`
  leidt tot `needs_intervention=False` en `reason="user_opted_out_art22"`.

### 1.8 Foutafhandeling
- `FileNotFoundError` als het scenario-bestand ontbreekt.
- `ValueError` als het pad geen bestand is of buiten de project-root valt.
- `ValueError` als het YAML-formaat ongeldig is.
- Fouten in individuele scenario's worden als `errors` in `EvalResult` gerapporteerd;
  ze stoppen de rest van de evaluatie niet.

### 1.9 Telemetry / logging
- `logger.warning("eval_scenario_failed", scenario_id=..., errors=...)` bij falende
  scenario's.

### 1.10 Acceptatiecriteria
- [ ] `EvalHarness` laadt 5 scenario's uit YAML.
- [ ] Alle 5 scenario's slagen in `tests/unit/learning/test_eval_harness.py`.
- [ ] `MockSuggestionProvider` wordt per scenario geconfigureerd.
- [ ] `consent_opt_out` scenario toont `reason="user_opted_out_art22"`.
- [ ] `llm_failure` scenario toont `needs_intervention=True` met lege suggestie.
- [ ] Ruff en pyright rapporteren 0 nieuwe errors op de gewijzigde bestanden.

### 1.11 Integratoruitleg
- Voeg nieuwe scenario's toe aan `tests/unit/learning/fixtures/eval_scenarios.yaml`
  zonder code te wijzigen.
- Draai `pytest tests/unit/learning/test_eval_harness.py -v` als onderdeel van CI.
- Gebruik `mock_response` voor de verwachte suggestie en `raise_error: true` om
  LLM-foutpaden te testen.

### 1.12 Trainingssamenvatting
- Actor: ontwikkelaar / CI-pipeline
- Voorwaarde: YAML-fixture met geldige scenario's
- Actie: `await EvalHarness(path).run()`
- Systeemverwerking: laad scenario's, bouw mock service, vergelijk output
- Succesrespons: `EvalReport` met `passed == total`
- Foutrespons: `EvalReport` met `failed > 0` of exception bij ongeldig pad/YAML

---

## 2. Golden scenario YAML

### 2.1 Doel
Beschrijf deterministische invoer/verwachte-uitvoer paren voor
`analyze_struggle()` op een plek die makkelijk uitbreidbaar is.

### 2.2 Technische beschrijving
- Bestand: `tests/unit/learning/fixtures/eval_scenarios.yaml`
- 5 scenario's:
  1. `no_struggle` -- alle indicatoren nul, score 0.0, geen interventie.
  2. `multi_factor_crisis` -- alle indicatoren op maximum, score 1.0, suggestie
     van mock provider.
  3. `below_threshold` -- matige struggle, score 0.35, geen interventie.
  4. `consent_opt_out` -- hoge score maar `ai_interventions=False`, geen suggestie.
  5. `llm_failure` -- hoge score maar provider gooit fout, geen crash.

### 2.3 Acceptatiecriteria
- [ ] YAML bevat exact 5 scenario's.
- [ ] Alle `expected.score` waarden zijn arithmetisch correct.
- [ ] Geen non-ASCII tekens in code-waarden.
- [ ] Geen echte secrets of tenant-specifieke productiedata.

---

## Open aannames, risico's en ontbrekende informatie

- Aanname: `WeightedStruggleScore` blijft ongewijzigd; bij wijziging van gewichten
  of drempelwaarde moeten de scenario's worden bijgewerkt.
- Aanname: `PracticalTwinService.analyze_struggle()` blijft hetzelfde signatuur
  behouden.
- Risico: het harnas test alleen het gedrag van `analyze_struggle()`; het test niet
  de kwaliteit van echte LLM-suggesties.
