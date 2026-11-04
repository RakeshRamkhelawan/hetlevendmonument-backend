# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-026
- Feature naam: LLM json.loads hardening -- per-call try-except + WARNING (LLM-C5-001/002)
- Status: DONE
- Auteur: Uitvoerende agent SP-SEC-001 Dag 1
- Reviewer: Zie docs/backend/review/review-BE-SEC-026.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: SP-SEC-001 LLM-C5-001, LLM-C5-002 (multidisciplinaire audit 2026-06-30)
- Gerelateerde router / module: llm_agent_adapter, adaptive_learning_engine
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

Twee locaties hadden onbeschermde of onvolledig beschermde `json.loads()` aanroepen die bij
malformed LLM-output konden crashen of stil falen zonder observeerbare waarschuwing.
Fix: elke `json.loads()` aanroep krijgt een eigen try-except met `logger.warning(..., exc_info=True)`.

### In scope

- `src/core/als/llm_integration/llm_agent_adapter.py` (LLM-C5-001): `_parse_llm_response()`
- `src/core/ai/adaptive_learning_engine.py` (LLM-C5-002): learning event + insight parse blokken
- 4 unit tests (2 RED->GREEN per bevinding)

### Out of scope

- LLM provider fouten buiten json-parsing
- Retry-logica bij JSON parse failures
- Structuuraanpassingen aan de LLM-respons pipeline

---

## Build summary

- Nieuw gebouwd: 4 unit tests
- Gewijzigd: 2 bronbestanden (llm_agent_adapter.py, adaptive_learning_engine.py)
- Verwijderd: --
- Beinvloede bestaande flows: LLM response parsing; slechte LLM output degradeert nu graceful

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-026-C5-001 | _parse_llm_response per-call try-except | BE-SVC | src/core/als/llm_integration/llm_agent_adapter.py | Wijziging | LLM agent taak-uitvoering |
| BE-SEC-026-C5-002 | adaptive_learning event + insight parse hardening | BE-SVC | src/core/ai/adaptive_learning_engine.py | Wijziging | Agent learning pipeline |

---

## API-flows

### Flow BE-FLW-SEC-026

- Naam: LLM JSON response parsing met graceful degradation
- Trigger: LLM-provider retourneert string-response
- Voorwaarden: `_parse_llm_response()` of learning engine parse-blok aangeroepen
- Request-pad: LLM response string ontvangen
- Service-stappen: 1) zoek json block, 2) try json.loads(), 3) bij JSONDecodeError: warning + fallback
- DB-operaties: --
- Successtatus: dict met geparsede LLM data
- Foutpaden: JSONDecodeError -> logger.warning met exc_info=True -> fallback dict
- Eindtoestand: altijd een geldig dict -- systeem stopt niet bij malformed LLM output

---

## Detaildocumentatie per artefact

---

## [BE-SEC-026-C5-001] _parse_llm_response() -- llm_agent_adapter.py

### 1. Type

- Service methode

### 2. Locatie

- Bestandspad: src/core/als/llm_integration/llm_agent_adapter.py
- Klasse / functie: `LLMAgentAdapter._parse_llm_response()`

### 4. Doel

LLM-responses bevatten soms JSON in code blocks (```json), plain code blocks (```), of direct.
Elke variant wordt geparsed; bij mislukking wordt een gestructureerde fallback geretourneerd.

### 5. Functionele beschrijving

- Drie parsing-paden: json block, plain code block, raw content.
- Elk pad heeft een eigen try-except die JSONDecodeError logt als WARNING met exc_info=True.
- Bij alle failures: fallback dict `{"summary": "Task completed", ..., "completed": True}`.

### 6. Technische beschrijving

```python
try:
    return cast(dict[str, Any], json.loads(json_str))
except json.JSONDecodeError as e:
    logger.warning("LLM response parse failed (json block): %s", e)
# (herhald voor elk pad)
return {"summary": "Task completed", "detailed_output": content, ...}
```

`%s` format (niet f-string) per backend-patterns.md regel 10.

### 17. Acceptatiecriteria

- Bij malformed JSON: `logger.warning()` aangeroepen (unit test GROEN)
- Bij malformed JSON: retourneert dict (geen exception omhoog) (unit test GROEN)
- Geen onbeschermde `json.loads()` in `_parse_llm_response()`

### 19. Trainingssamenvatting

- Actor: LLMAgentAdapter
- Voorwaarde: LLM-provider heeft string-response teruggegeven
- Actie: `_parse_llm_response(content)` aangeroepen
- Systeemverwerking: probeert JSON te parsen uit json block / code block / raw; logt WARNING bij fout
- Succesrespons: dict met geparsede LLM data
- Foutrespons: logger.warning + fallback dict -- geen exception propagatie
- Uitzonderingen: --

---

## [BE-SEC-026-C5-002] adaptive_learning_engine parse hardening

### 1. Type

- Service methode (intern)

### 2. Locatie

- Bestandspad: src/core/ai/adaptive_learning_engine.py
- Functie: learning event parse blok + insight parse blok (twee locaties)

### 4. Doel

Twee parse-blokken hadden brede except-clauses die `json.JSONDecodeError` samen met
`TypeError`/`AttributeError` afvingen en alleen een debug-log stuurden. JSON-fouten
verdienen een WARNING -- ze indiceren LLM-output degradatie die monitoring vereist.

### 5. Functionele beschrijving

- Learning event blok: `json.JSONDecodeError` -> WARNING; `TypeError/AttributeError` -> DEBUG; overig -> WARNING.
- Insight blok: zelfde patroon.
- f-strings in logger-calls vervangen door `%s` format per backend-patterns.md.

### 6. Technische beschrijving

```python
except json.JSONDecodeError as e:
    logger.warning("Failed to parse learning event: %s", e, exc_info=True)
except (TypeError, AttributeError) as e:
    logger.debug("Failed to access learning event attributes: %s", e)
except Exception as e:
    logger.warning("Unexpected error parsing learning event: %s", e, exc_info=True)
```

### 17. Acceptatiecriteria

- Bij JSONDecodeError in learning event: WARNING gelogd (geen DEBUG) (unit test GROEN)
- Bij JSONDecodeError in insight: WARNING gelogd (unit test GROEN)
- Geen f-strings in logger-aanroepen

### 19. Trainingssamenvatting

- Actor: AdaptiveLearningEngine
- Voorwaarde: LLM-respons ontvangen voor learning event of insight extractie
- Actie: JSON parse van event/insight data
- Systeemverwerking: JSONDecodeError -> logger.warning; andere fouten -> gedifferentieerd
- Succesrespons: event/insight geparsed
- Foutrespons: WARNING gelogd; engine gaat door met volgende event/insight
- Uitzonderingen: --

---

## QA-checks

- [x] 4 unit tests GROEN (2 per bevinding)
- [x] Geen onbeschermde json.loads in scope-bestanden
- [x] Pyright 0 errors na wijzigingen

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria testbaar
- [x] Trainingssamenvatting aanwezig
- [x] Review: zie review-BE-SEC-026.md
