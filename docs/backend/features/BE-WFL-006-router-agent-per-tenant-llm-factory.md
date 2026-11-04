# BE-WFL-006 -- RouterAgentService Per-Tenant LLM Credentials via LLMProviderFactory

## Metadata

- Feature ID: BE-WFL-006
- Feature naam: RouterAgentService Per-Tenant LLM Credentials via LLMProviderFactory
- Status: GEREED
- Auteur: Rakesh Ramkhelawan
- Reviewer: self-review (< 50 regels, 1 bestand)
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-ADR023 fase-2 open items
- Gerelateerde router / module: `src/core/agents/router_agent_service.py`
- Gerelateerde database tabellen: geen
- Versie: 1.0

---

## Doel en scope

### Doel

RouterAgentService instantieerde GeminiProvider() globaal zonder tenant-context, waardoor alle
tenants dezelfde environment-variabele credentials deelden. Na deze fix worden per-tenant
credentials opgezocht via LLMProviderFactory.get_provider(tenant_id, provider_type="gemini").

### In scope

- Verwijder directe `GeminiProvider()` instantiatie uit `execute_request()`
- Vervang door `LLMProviderFactory.get_provider(tenant_id=tenant_id, provider_type="gemini")`
- Voeg module-niveau import toe voor `LLMProviderFactory`

### Out of scope

- `LLMProviderFactory.set_tenant_config()` wiring aan tenant onboarding (apart sprint item)
- Ollama / andere providers per-tenant (enkel Gemini was direct geinstantieerd)
- Aanmaken van tenant-specifieke credentials (uitganspunt: al geconfigureerd via factory)

---

## Build summary

- Nieuw gebouwd: --
- Gewijzigd: `src/core/agents/router_agent_service.py` (import + GeminiProvider -> LLMProviderFactory)
- Verwijderd: directe `from src.core.llm.gemini_provider import GeminiProvider` inline import
- Beinvloede bestaande flows: execute_request() Gemini-pad

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SVC-WFL-006a | RouterAgentService Gemini -> LLMProviderFactory | Service-wijziging | `src/core/agents/router_agent_service.py` | Wijziging | BE-WFL-006 |

---

## API-flows

### Flow: RouterAgentService.execute_request() Gemini-pad

- Naam: Router execute_request Gemini per-tenant
- Trigger: `await router.execute_request(query, tenant_id="tenant_42")`
- Voorwaarden: `route_request()` retourneert `suggested_model` met "gemini" in de naam
- Service-stappen:
  1. `route_request(query)` -- bepaal suggested_model
  2. `LLMProviderFactory.get_provider(tenant_id=tenant_id, provider_type="gemini")` -- haal tenant-specifieke provider
  3. Valideer `getattr(provider, "api_key", None)` -- ValueError als geen key
  4. `await provider.text_completion(query)` -- uitvoeren
  5. Bij fout: fallback naar Ollama (`executed_by="ollama_fallback"`)
- DB-operaties: geen
- Successtatus: `{"executed_by": "gemini_provider", "tenant_id": tenant_id, ...}`
- Foutpaden: `{"executed_by": "ollama_fallback", ...}` bij ontbrekende key of provider-fout
- Eindtoestand: LLM-response teruggegeven; geen state-wijziging

---

## Detaildocumentatie per artefact

---

## [BE-SVC-WFL-006a] RouterAgentService Gemini per-tenant fix

### 1. Type

Service-wijziging

### 2. Locatie

- Bestandspad: `src/core/agents/router_agent_service.py`
- Klasse / functie: `RouterAgentService.execute_request()`

### 3. Gerelateerde flow

BE-WFL-006

### 4. Doel

Tenant-isolatie voor Gemini LLM-aanroepen: elke tenant gebruikt eigen API-credentials
(indien geconfigureerd) in plaats van gedeelde env-var credentials.

### 5. Functionele beschrijving

Voor de fix deelden alle tenants dezelfde Gemini API-key (via environment-variabele).
Na de fix raadpleegt RouterAgentService de LLMProviderFactory die per-tenant credentials
kan teruggeven als die geconfigureerd zijn, met fallback naar env-var.

### 6. Technische beschrijving

VOOR:
```python
from src.core.llm.gemini_provider import GeminiProvider
provider = GeminiProvider()
if not provider.api_key:
    raise ValueError("No Gemini API Key found")
```

NA:
```python
from src.core.llm.provider_factory import LLMProviderFactory  # module-niveau import
provider = LLMProviderFactory.get_provider(
    tenant_id=tenant_id, provider_type="gemini"
)
if not getattr(provider, "api_key", None):
    raise ValueError("No Gemini API Key found for tenant")
```

`LLMProviderFactory.get_provider()` gebruikt `cls._tenant_configs[tenant_id]` als die bestaat,
anders env-var fallback. Geen API-contract wijziging voor callers.

### 7. Zichtbaarheids- en toegangsregels

- Interne service-laag; geen HTTP-exposure
- Tenant-isolatie: `tenant_id` uit workflowcontext doorgegeven
- Feature flag: geen

### 8. Request-specificatie

n.v.t. (service-laag)

### 9. Response-specificatie

n.v.t.

### 10. Validaties en constraints

- `getattr(provider, "api_key", None)` gebruikt i.p.v. `provider.api_key` voor defensieve check

### 11. Business rules

- Als geen Gemini-key beschikbaar voor de tenant: foutpad -> Ollama fallback (niet hard-fail)
- Fallback-gedrag ongewijzigd: `executed_by="ollama_fallback"`

### 12. Afhankelijkheden

- `src/core/llm/provider_factory.py` -- LLMProviderFactory (al volledig geimplementeerd)

### 13. Foutafhandeling

- `ValueError("No Gemini API Key found for tenant")` -> gevangen in inner try/except -> Ollama fallback
- Provider text_completion fout -> gevangen -> Ollama fallback

### 14. Transacties en dataïntegriteit

- Geen transacties

### 15. Telemetry / logging / tracing

- `logger.warning("Gemini execution failed: ... -- falling back to Ollama")` bij fout
- `tenant_id` aanwezig in return-dict voor tracing

### 16. Caching

- LLMProviderFactory kan intern cachen op `f"{tenant_id}:{provider_type}"`

### 17. Acceptatiecriteria

- `execute_request(query, tenant_id="X")` aanroep met gemini-route -> `LLMProviderFactory.get_provider(tenant_id="X", provider_type="gemini")` aangeroepen
- Zonder tenant_id: `get_provider(tenant_id=None, ...)` -> env-var fallback
- Bij ontbrekende api_key: executie valt terug op Ollama, geen crash

### 18. Integratoruitleg

- Geen aanpassing vereist voor callers van `execute_request()`
- Per-tenant Gemini-credentials configureren via `LLMProviderFactory.set_tenant_config(tenant_id, {"gemini_api_key": "..."})`

### 19. Trainingssamenvatting

- Actor: RouterAgentService
- Voorwaarde: route_request() wijst naar gemini-model; tenant_id aanwezig of None
- Actie: execute_request(query, tenant_id=tenant_id)
- Systeemverwerking: LLMProviderFactory.get_provider(tenant_id, "gemini") -> text_completion
- Succesrespons: {"executed_by": "gemini_provider", "tenant_id": tenant_id, ...}
- Foutrespons: {"executed_by": "ollama_fallback", ...} bij ontbrekende key of provider-fout
- Uitzonderingen: zonder api_key: ValueError gevangen, fallback naar Ollama

---

## Integratorhandleiding

### Voor service-consumenten

- Geen API-wijziging; `execute_request(query, tenant_id=...)` interface ongewijzigd
- Per-tenant Gemini-credentials: configureer via `LLMProviderFactory` voor tenant onboarding
- Ontbrekende credentials resulteren in stille Ollama-fallback, niet in een fout

---

## Open aannames

- LLMProviderFactory.set_tenant_config() koppeling aan tenant-onboarding is apart sprint item
- Fase 1: env-var fallback volstaat voor alle tenants zonder expliciete config

## Open vragen

- --

## Risico's

- Laag: als geen tenant-config geconfigureerd, valt alle verkeer terug op dezelfde env-var (bestaand gedrag)

---

## QA-checks

- [x] Gemini-pad test: LLMProviderFactory.get_provider aangeroepen met juiste tenant_id
- [x] None tenant_id test: get_provider(tenant_id=None, ...) aangeroepen
- [x] Bestaande tests ongewijzigd groen (regressie-check)
- [ ] Integratietest met echte per-tenant config (fase 2)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Service geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar en groen
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
