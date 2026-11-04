# Review: BE-AGT-032 Orchestration DI Consolidation naar dependencies.py

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

## B. SAMENVATTING

De spec beschrijft de consolidatie van de orchestration DI-factories in `src/core/api/v1/orchestration/dependencies.py` en de verwijdering van directe `src.core.agents.*` imports uit de sub-routers. De lijst van opgeloste violations is concreet en de testresultaten zijn gunstig. De huidige broncode wijkt op een aantal punten af van de geillustreerde snippet, maar de intentie en het resultaat zijn correct.

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- De spec toont `get_critic_agent()` dat `CriticAgent(agent_id=f"critic_t{tenant_id}")` instantieert. De huidige code gebruikt `CriticAgent(tenant_id=tenant_id)`.
- `get_master_orchestrator()` in de huidige code delegeert naar `get_orchestrator_singleton()` en heeft geen lokaal `_orchestrator_cache`; de spec impliceert nog het eerdere lokale cache-patroon.
- `get_agent_router()` en `_get_redis_client_fail_graceful()` zijn in de broncode aanwezig maar niet in de spec gemarkeerd als nieuwe/gewijzigde items.
- Trainingssamenvatting ontbrak; wordt in deze ronde toegevoegd.

### 2. Functionele onduidelijkheden

- De spec noemt dat `safe_get_tenant_id` HTTP 401 raised, maar legt niet uit wanneer dat optreedt (ontbrekende/ongeldige JWT of tenant context).

### 3. Technische onduidelijkheden

- De spec beschrijft `ARG001 noqa` op `_critic`, maar de huidige docstring legt beter uit dat dit de CriticMixin-cache pre-wires.
- Het verschil tussen lokale `_critic_cache` / `_health_monitor_cache` en de singleton-caches in `agent_router_agent.py` / `master_orchestrator_agent.py` is niet duidelijk gescheiden.

### 4. Ontbrekende foutstatussen en edge cases

- Geen beschrijving van het gedrag bij Redis-uitval: `_get_redis_client_fail_graceful()` retourneert `None`, waarna de router/orchestrator zonder cache-tier verder werkt.
- `clear_tenant_cache()` is niet atomair over de vier caches; dat risico is in de code gedocumenteerd maar niet in de spec.

### 5. Acceptatiecriteria problemen

- Geen expliciete acceptatiecriteria opgenomen; alleen testresultaten.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratoruitleg is beperkt. Een voorbeeld van een endpoint handler die `Depends(get_master_orchestrator)` gebruikt ontbreekt.

### 7. Trainingsdata problemen

- Trainingssamenvatting ontbrak.

### 8. Structuur- en consistentieproblemen

- Code snippet is outdated ten opzichte van de huidige `dependencies.py`.

### 9. Risico's voor implementatie, security of QA

- Geen materiele risico's. Tenant-isolatie is correct geimplementeerd via `safe_get_tenant_id` en per-tenant caches.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|--------------|----------|----------------------------|--------------------|
| Medium | Implementatie snippet | `get_critic_agent()` en `get_master_orchestrator()` snippets komen niet overeen met huidige code. | Spec en code lopen uit de pas. | Werk snippet naar huidige implementatie. |
| Low | Coverage | `get_agent_router()` en `_get_redis_client_fail_graceful()` zijn niet opgenomen in de inventaris. | Lezers missen belangrijke factories. | Voeg toe aan Backend Inventory. |
| Low | Foutafhandeling | Redis-uitval pad en niet-atomaire `clear_tenant_cache()` ontbreken in spec. | Operatoren moeten weten dat cache-uitval graceful is en dat cache-cleanup een race kan bevatten. | Documenteer beide gedragingen. |
| Low | Acceptatiecriteria | Geen expliciete criteria. | QA weet niet zonder tests wat "klaar" is. | Voeg 3-4 criteria toe. |
| Low | Trainingssamenvatting | Sectie ontbrak. | Vereiste voor LLM-training. | Toegevoegd in deze ronde. |

## E. ONTBREKENDE ITEMS

- Beschrijving van `get_agent_router()` en Redis fail-graceful helper.
- Actuele code snippet van `dependencies.py`.

## F. VERBETERDE TEKSTVOORSTELLEN

Backend Inventory mag uitbreiden met:

| BE-DEP-032-1 | `get_agent_router` | DI factory | `src/core/api/v1/orchestration/dependencies.py` | Nieuw | Router agent injectie |
| BE-DEP-032-2 | `_get_redis_client_fail_graceful` | helper | `src/core/api/v1/orchestration/dependencies.py` | Nieuw | Redis cache tier degradatie |

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: Ja.
- Geschikt voor QA en geautomatiseerd testen: Ja.
- Geschikt voor LLM-training: Ja, na toevoeging Trainingssamenvatting.
- Geschikt voor integratorhandleiding / API-documentatie: Ja, met kleine aanvulling.
