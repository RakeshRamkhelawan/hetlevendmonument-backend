# Review BE-EP-020 — ALS Ping via SignalBus

## A. Eindoordeel

APPROVED

## B. Samenvatting

De specificatie beschrijft een kleine maar belangrijke fix: `POST /als/agents/{agent_id}/ping` bouwt nu een echt `Signal`-object en emitteert dit via de orchestrator SignalBus in plaats van een hardcoded succesrespons te retourneren. De broncode in `src/core/api/v1/als/als_agents_router.py` bevestigt de implementatie, inclusief timeout (504) en bus-fout (503) afhandeling.

## C. Bevindingen per categorie

### 1. Coverage gaps

- Geen. Endpoint, request/response, foutpaden en tests zijn beschreven.

### 2. Functionele onduidelijkheden

- Geen. De flow is helder.

### 3. Technische onduidelijkheden

- De spec noemt `get_orchestrator(tenant_id).signal_bus.emit(signal)` met 30s timeout. Broncode bevestigt `asyncio.wait_for(..., timeout=ALS_ORCHESTRATOR_TIMEOUT_SECONDS)`.
- De spec noemt `SignalTier.COGNITIVE`. Broncode bevestigt `tier=SignalTier.COGNITIVE`.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt 504, 503, 401/403. Dat dekt de belangrijkste paden.
- Een edge case ontbreekt: cooldown in SignalBus kan het signaal silent droppen, maar het endpoint retourneert dan 200. De spec noemt dit correct als "by design".

### 5. Acceptatiecriteria problemen

- De spec verwijst naar 6 tests in `tests/unit/test_sp_e06_small_fixes.py::TestALSPing`. Criteria zijn impliciet testbaar.

### 6. Integratorhandleiding / API-uitleg problemen

- De Trainingssamenvatting in tabelvorm is voldoende.

### 7. Trainingsdata problemen

- Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- Compacte feature-note, passend voor een kleine endpoint-fix.

### 9. Risico's voor implementatie, security of QA

- Laag risico. Timeout en foutafhandeling zijn aanwezig.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Geen | - | - | - | - |

## E. Ontbrekende items

- Geen.

## F. Verbeterde tekstvoorstellen

- Geen.

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
