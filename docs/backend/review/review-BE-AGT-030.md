# Review: BE-AGT-030 IAgentRuntime Facade + import-linter Contract 2+3

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

## B. SAMENVATTING

De spec beschrijft correct het doel en de structuur van de ADR-034 agent-runtime facade in `src/core/agents/api.py`. De drie gesignaleerde Protocols (`IAgentRuntime`, `ICapabilityRegistry`, `IHealthMonitor`) en de lazy singleton-accessors zijn aanwezig in de broncode. De tests in `tests/unit/agents/test_agents_facade.py` en `tests/architecture/test_adr034_contracts.py` dekken de belangrijkste garanties. De documentatie is functioneel bruikbaar, maar heeft een aantal kleine inconsistenties en onvolledigheden ten opzichte van het verplichte feature-doc template.

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- `ICacheBackend` Protocol is geexporteerd in `src/core/agents/api.py` (`__all__`) maar komt in de samenvatting niet voor; de spec noemt alleen drie Protocols.
- De spec noemt "Contract 2+3" (legacy nummering), terwijl `.importlinter` deze contracten `agent_runtime_boundary` (Contract 6) en `agent_runtime_no_db` (Contract 7) noemt.
- Trainingssamenvatting ontbrak; wordt in deze reviewronde toegevoegd.

### 2. Functionele onduidelijkheden

- Geen. De facade-gedragingen (raise RuntimeError bij niet-registratie, warning bij overschrijven) zijn duidelijk.

### 3. Technische onduidelijkheden

- De spec stelt dat Contract 6/7 "bewaken dat de facade zelf geen circulaire afhankelijkheden krijgt". Contract 6 verbiedt imports van `src.core.api` in `src.core.agents.api`; Contract 7 verbiedt directe database-coupling in het hele `src.core.agents` package (Dag 5 uitbreiding). Dit verschil is niet expliciet uitgewerkt.

### 4. Ontbrekende foutstatussen en edge cases

- `register_agent_runtime()` kan een waarschuwing loggen bij herregistratie; dit is wel in de code maar niet in de spec beschreven als observable gedrag.
- `get_health_monitor()` retourneert `None` als er niets is geregistreerd, in tegenstelling tot `get_agent_runtime()` die een RuntimeError gooit; dit contrast ontbreekt.

### 5. Acceptatiecriteria problemen

- Geen expliciete acceptatiecriteria in de spec opgenomen. De testresultaten worden wel gerapporteerd, maar zijn geen vervanging voor testbare criteria.

### 6. Integratorhandleiding / API-uitleg problemen

- De integrator-uitleg is beperkt tot de samenvatting. Een voorbeeld van een correcte import (`from src.core.agents.api import IAgentRuntime, get_agent_runtime`) ontbreekt.

### 7. Trainingsdata problemen

- De Trainingssamenvatting ontbrak. Zonder deze sectie is de spec minder geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- Gebruik van "Contract 2+3" versus huidige contractnamen in `.importlinter` is verwarrend voor toekomstige lezers.

### 9. Risico's voor implementatie, security of QA

- Geen materiele risico's. De singleton-registratie is per workerproces, wat correct is voor Gunicorn + Uvicorn.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|--------------|----------|----------------------------|--------------------|
| Medium | Samenvatting / .importlinter | Spec verwijst naar "Contract 2+3", configuratie gebruikt `agent_runtime_boundary` en `agent_runtime_no_db`. | Verkeerde contractnummers kunnen reviewers op het verkeerde spoor zetten. | Werk nummering af naar huidige `.importlinter` namen, of verwijs naar beide. |
| Low | Samenvatting | `ICacheBackend` ontbreekt in de opsomming van Protocols. | Lezers missen een geexporteerd public interface. | Voeg `ICacheBackend` toe aan de lijst van gedefinieerde Protocols. |
| Low | Detailsecties | Geen volledige per-artefact secties (request/response, auth, caching, etc.) conform template. | Het is een utility/facade, maar het template vraagt om expliciete afwegingen. | Voeg verkorte per-artefact secties toe of expliciteer waarom ze niet van toepassing zijn. |
| Low | Foutafhandeling | Contrast tussen `get_agent_runtime()` (RuntimeError) en `get_health_monitor()` (None) niet beschreven. | Callers moeten weten dat health-monitor optioneel is en runtime niet. | Documenteer het verschil in foutgedrag. |
| Low | Trainingssamenvatting | Sectie ontbrak. | Vereiste voor LLM-training en feature-doc workflow. | Toegevoegd in deze ronde. |

## E. ONTBREKENDE ITEMS

- Verkorte per-artefact detailsectie voor `ICacheBackend`.
- Verduidelijking van contractnummering versus `.importlinter`.

## F. VERBETERDE TEKSTVOORSTELLEN

Samenvatting mag luiden:

> `src/core/agents/api.py` is aangemaakt als enige publieke toegangspoort voor `agent_runtime`. Vier runtime-checkable Protocols zijn gedefinieerd: `IAgentRuntime`, `ICacheBackend`, `ICapabilityRegistry` en `IHealthMonitor`. Twee lazy singletons met `register_*()` / `get_*()` accessors zorgen voor app-lifespan wiring. Import-linter Contract 6 (`agent_runtime_boundary`) en Contract 7 (`agent_runtime_no_db`) bewaken de facade-grenzen.

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: Ja.
- Geschikt voor QA en geautomatiseerd testen: Ja, tests zijn aanwezig en slagen.
- Geschikt voor LLM-training: Ja, na toevoeging Trainingssamenvatting.
- Geschikt voor integratorhandleiding / API-documentatie: Ja, met kleine aanvulling.
