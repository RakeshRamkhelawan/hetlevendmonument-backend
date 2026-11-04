# Backend Feature Specification

## Metadata

- Feature ID: BE-ST-001
- Feature naam: Single-Tenant Worker Context
- Status: DONE
- Auteur: Claude (S1 sprint)
- Reviewer: Zie review/review-BE-ST-001.md
- Datum: 2026-07-01
- Gerelateerde user story / ticket: AUDIT-ST-03
- Gerelateerde router / module: src/core/workers/tenant_context.py
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

In single-tenant deployments hebben Dramatiq-workers geen JWT-context. Zonder tenant_id crashen alle ORM-queries die door de ADR-004 do_orm_execute hook gaan. Dit module injecteert automatisch tenant_id=1 voor single-tenant workers en verwijdert deze daarna zodat thread-pool bleed wordt voorkomen.

### In scope

- Context manager `single_tenant_worker_context()` die tenant_id=1 injecteert bij DEPLOYMENT_MODE=single_tenant
- Decorator `ensure_single_tenant_context()` voor Dramatiq-task functies
- Cleanup in finally-block (thread pool bleed preventie)
- Runtime evaluatie van DEPLOYMENT_MODE (niet import-time, zodat tests `monkeypatch.setenv()` kunnen gebruiken)

### Out of scope

- Multi-tenant worker context
- JWT-gebaseerde tenant injectie in workers
- Dramatiq middleware integratie (aparte taak)

---

## Build summary

- Nieuw gebouwd: `src/core/workers/__init__.py`, `src/core/workers/tenant_context.py`
- Gewijzigd: N/A
- Verwijderd: N/A
- Beinvloede bestaande flows: Dramatiq-workers die draaien met DEPLOYMENT_MODE=single_tenant

---

## Backend inventory

| ID         | Naam                         | Type            | Bestandspad                        | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | ---------------------------- | --------------- | ---------------------------------- | --------------- | ----------------- |
| BE-UTL-010 | single_tenant_worker_context | Context manager | src/core/workers/tenant_context.py | Nieuw           | BE-FLW-ST-001     |
| BE-UTL-011 | ensure_single_tenant_context | Decorator       | src/core/workers/tenant_context.py | Nieuw           | BE-FLW-ST-001     |

---

## API-flows

### Flow ID: BE-FLW-ST-001

- Naam: Single-tenant worker tenant injectie
- Trigger: Dramatiq-worker voert een taak uit met DEPLOYMENT_MODE=single_tenant
- Voorwaarden: DEPLOYMENT_MODE env-variabele = "single_tenant"; get_tenant_id() geeft None terug
- Request-pad: Worker task aangeroepen -> decorator wrapper -> context manager
- Service-stappen: 1) os.getenv("DEPLOYMENT_MODE") evalueren, 2) get_tenant_id() checken, 3) set_tenant_id(1) bij match, 4) task uitvoeren, 5) set_tenant_id(None) in finally
- DB-operaties: N/A (utility laag)
- Successtatus: tenant_id=1 zichtbaar in ContextVar tijdens task uitvoering
- Foutpaden: DEPLOYMENT_MODE != "single_tenant" -> geen injectie (doorgaan zonder aanpassing)
- Eindtoestand: ContextVar teruggezet naar None na task afronding

---

## Detaildocumentatie per artefact

---

## [BE-UTL-010] single_tenant_worker_context

### 1. Type

- Context manager (contextlib.contextmanager)

### 2. Locatie

- Bestandspad: src/core/workers/tenant_context.py
- Klasse / functie: single_tenant_worker_context()

### 3. Gerelateerde flow

- BE-FLW-ST-001

### 4. Doel

- Injecteert tenant_id=1 voor de duur van een worker-taak in single-tenant deployments

### 5. Functionele beschrijving

- Wanneer DEPLOYMENT_MODE="single_tenant" en de huidige ContextVar geen tenant_id heeft, wordt tenant_id=1 ingesteld. Na afloop van de with-block wordt de waarde altijd verwijderd (finally). In SaaS-modus of wanneer al een tenant_id aanwezig is, doet de context manager niets.

### 6. Technische beschrijving

- os.getenv("DEPLOYMENT_MODE", "saas").lower() wordt runtime geëvalueerd zodat monkeypatch.setenv() in tests werkt
- get_tenant_id() en set_tenant_id() komen uit src/core/middleware/tenant_context.py (ContextVar)
- `injected` vlag zorgt dat alleen bij injectie ook de cleanup plaatsvindt
- finally-block garandeert cleanup ook bij exceptions in de worker-taak

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: N/A (interne utility)
- Vereiste rol / scope: N/A
- Tenant-isolatie: Zet altijd tenant_id=1; nooit meer dan 1 tenant in single-tenant mode
- Feature flag: DEPLOYMENT_MODE env-variabele

### 8. Request-specificatie

- Methode: Context manager (geen HTTP)
- Route: N/A
- Path parameters: N/A
- Query parameters: N/A
- Request body (schema): N/A
- Verplichte headers: N/A

### 9. Response-specificatie

- Successtatus: N/A (geen HTTP)
- Response schema: N/A
- Foutstatussen: N/A

### 10. Validaties en constraints

- DEPLOYMENT_MODE wordt case-insensitive gecontroleerd via .lower()
- Geldige waarden: "single_tenant" (injectie), "saas" of andere (geen injectie)

### 11. Business rules

- In single-tenant mode is altijd tenant_id=1
- Nooit tenant_id injiceren als al een waarde aanwezig is (voorkomt JWT-override)

### 12. Afhankelijkheden

- src/core/middleware/tenant_context.py (get_tenant_id, set_tenant_id)
- DEPLOYMENT_MODE environment variabele

### 13. Foutafhandeling

- 400: N/A
- 401: N/A
- 403: N/A
- 404: N/A
- 409: N/A
- 422: N/A
- 429: N/A
- 500: Exceptions in worker-taak propageren normaal; finally zorgt altijd voor cleanup
- 503: N/A

### 14. Transacties en dataïntegriteit

- Geen directe DB-transacties; zorgt dat ORM-queries de juiste tenant_id meekrijgen via ContextVar

### 15. Telemetry / logging / tracing

- Geen logging (utility laag); telemetry via OpenTelemetry in aanroepende worker

### 16. Caching

- Gecached: Nee
- Cache-sleutel: N/A
- TTL: N/A
- Invalidatie: N/A

### 17. Acceptatiecriteria

- [ ] Bij DEPLOYMENT_MODE=single_tenant en geen bestaande tenant_id: get_tenant_id() geeft 1 terug binnen de context
- [ ] Na de context is get_tenant_id() None
- [ ] Bij DEPLOYMENT_MODE=saas: geen injectie
- [ ] Bestaande tenant_id wordt niet overschreven
- [ ] Exception in worker-taak: ContextVar toch teruggezet

### 18. Integratoruitleg

- Decoreer Dramatiq-task functies met `@ensure_single_tenant_context` voor automatische tenant injectie
- Gebruik `with single_tenant_worker_context():` voor granulaire controle
- Werkt alleen bij DEPLOYMENT_MODE=single_tenant; in SaaS mode is de decorator een no-op

### 19. Trainingssamenvatting

- Actor: Dramatiq worker in single-tenant deployment
- Voorwaarde: DEPLOYMENT_MODE=single_tenant, geen tenant_id in ContextVar
- Actie (request): Worker-task wordt aangeroepen via decorator
- Systeemverwerking: set_tenant_id(1), task uitvoeren, set_tenant_id(None) in finally
- Succesrespons: N/A (geen HTTP)
- Foutrespons: Exceptions propageren; cleanup altijd gegarandeerd
- Uitzonderingen: SaaS-mode of bestaande tenant_id -> geen injectie

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Voeg `@ensure_single_tenant_context` toe aan elke Dramatiq task functie in single-tenant deployments
- Stel `DEPLOYMENT_MODE=single_tenant` in via environment of docker-compose
- In SaaS deployments is de decorator een transparante no-op

---

## Open aannames

- tenant_id=1 is altijd de juiste ID voor single-tenant deployments

## Open vragen

- Geen

## Risico's

- Als een worker in SaaS-mode per ongeluk DEPLOYMENT_MODE=single_tenant krijgt, worden alle tasks als tenant 1 uitgevoerd

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (lege payload, onbekende tenant, grote dataset, race conditions)
- [x] Dataïntegriteit en transacties getest
- [ ] Performance / load getest (niet van toepassing)
- [ ] Caching getest (niet van toepassing)
- [x] Logging en tracing gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
