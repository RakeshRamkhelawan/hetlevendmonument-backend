# Review: BE-AGT-031 MasterOrchestratorRuntimeAdapter + Lifespan Wiring

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

## B. SAMENVATTING

De spec beschrijft correct hoe de ADR-034 facade operationeel wordt gemaakt via `MasterOrchestratorRuntimeAdapter` en lifespan-wiring in `src/core/api/main.py`. De broncode (`src/core/agents/runtime_adapter.py` en `src/core/api/main.py`) komt overeen met de beschreven intentie: thin delegation, `get_health()` met LLM-ready indicatie, en niet-fatale foutafhandeling bij startup. Enkele concrete afwijkingen tussen spec en code zijn echter niet gedocumenteerd.

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- De lifespan-code in de spec toont een vereenvoudigd snippet (`orchestrator = get_master_orchestrator(tenant_id=1)`). De werkelijke `main.py` roept `get_master_orchestrator(tenant_id=1, async_session_factory=get_db_session, redis_client=redis_client)` aan.
- De spec verwijst aan het eind naar `docs/backend/review/review-BE-AGT-006.md`; dat is een verkeerde review-link (BE-AGT-006 bestaat niet voor deze feature).
- Trainingssamenvatting ontbrak; wordt in deze ronde toegevoegd.

### 2. Functionele onduidelijkheden

- `route()` delegeert momenteel ook naar `process_task()`; de spec noemt dat dit een tijdelijke situatie is tot `AgentRouterAgent` wordt gewired. Dat is helder.
- De spec beschrijft dat startup niet blokkeert bij wiring-fout, maar het concrete pad (facade niet geregistreerd, RuntimeError bij gebruik) kan explicieter.

### 3. Technische onduidelijkheden

- De reden voor het meegeven van `async_session_factory` en `redis_client` aan de bootstrap-orchestrator (DB-backed discovery en cross-worker routing cache) is alleen in code-commentaar aanwezig, niet in de spec.

### 4. Ontbrekende foutstatussen en edge cases

- Geen expliciete beschrijving van het gedrag wanneer `orchestrator.initialize()` `False` retourneert: facade wordt niet geregistreerd en `get_agent_runtime()` zal later RuntimeError gooien.

### 5. Acceptatiecriteria problemen

- De testlijst is concreet (9/9 runtime adapter tests), maar acceptatiecriteria als zodanig ontbreken.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratoruitleg is beperkt. Een kort voorbeeld van het gebruik van `get_agent_runtime()` na startup ontbreekt.

### 7. Trainingsdata problemen

- Trainingssamenvatting ontbrak.

### 8. Structuur- en consistentieproblemen

- Review-link aan het eind wijst naar verkeerd ID.
- Code snippet en werkelijke main.py zijn niet consistent.

### 9. Risico's voor implementatie, security of QA

- Geen materiele risico's. De startup is fail-graceful en de adapter is stateless.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|--------------|----------|----------------------------|--------------------|
| Medium | Review-sectie | Verwijzing naar `review-BE-AGT-006.md` in plaats van `review-BE-AGT-031.md`. | Reviewers en toekomstige lezers kunnen de verkeerde review raadplegen. | Vervang door `docs/backend/review/review-BE-AGT-031.md`. |
| Medium | Implementatie / Lifespan | Code snippet laat `async_session_factory` en `redis_client` argumenten weg. | Spec en broncode lopen uit de pas; lezers missen belangrijke dependencies. | Werk snippet af naar werkelijke `main.py` aanroep. |
| Low | Detailsecties | Geen expliciete acceptatiecriteria. | QA kan niet zonder tests afleiden wat "klaar" betekent. | Voeg 3-4 testbare acceptatiecriteria toe. |
| Low | Trainingssamenvatting | Sectie ontbrak. | Vereiste voor LLM-training. | Toegevoegd in deze ronde. |

## E. ONTBREKENDE ITEMS

- Verduidelijking waarom `async_session_factory` en `redis_client` worden doorgegeven aan de bootstrap-orchestrator.
- Correcte review-link.

## F. VERBETERDE TEKSTVOORSTELLEN

Lifespan snippet:

```python
redis_client = await get_redis_client()
orchestrator = get_master_orchestrator(
    tenant_id=1,
    async_session_factory=get_db_session,
    redis_client=redis_client,
)
init_ok = await orchestrator.initialize()
if init_ok:
    register_agent_runtime(MasterOrchestratorRuntimeAdapter(orchestrator))
else:
    logger.warning("agent_runtime: facade NOT registered")
```

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: Ja.
- Geschikt voor QA en geautomatiseerd testen: Ja.
- Geschikt voor LLM-training: Ja, na toevoeging Trainingssamenvatting.
- Geschikt voor integratorhandleiding / API-documentatie: Ja, met kleine aanvulling.
