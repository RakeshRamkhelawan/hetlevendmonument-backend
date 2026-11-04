# Backend Feature Specification

## Metadata

- Feature ID: BE-LLM-001
- Feature naam: LLM-runtime productieklaar + no-mock-guard
- Status: APPROVED WITH MINOR GAPS
- Auteur: Kimi Code CLI
- Reviewer: code-reviewer subagent + quality-reviewer subagent (Laag A/C)
- Datum: 2026-07-05
- Gerelateerde user story / ticket: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 1
- Gerelateerde router / module: interne LLM infrastructuur
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: geen
- Versie: 1.0

---

## Doel en scope

### Doel

Zorgen dat de productie-omgeving nooit stil terugvalt op een mock-LLM, en dat DeepSeek als primaire provider correct wordt gedetecteerd, geconfigureerd en opgenomen in de failover-chain. Hiermee worden de audit-bevindingen LLM-ADR26-001, LLM-ADR26-002, LLM-ADR26-003 en LLM-MOCK-009 gesloten.

### In scope

- Productie-guard in `LLMService` die mock-fallback in productie blokkeert.
- Post-constructie-guard die een expliciet opgeloste `MockProvider` in productie afkeurt.
- `ProviderFactory.create_from_env()` hergebruikt `DEFAULT_LLM_MODEL` en `LLM_MODEL`.
- `docker-compose.prod.yml` declareert LLM-provider-config en API-keys uit env/Key Vault.
- `LLMFallbackChain` registreert DeepSeek-modellen (`deepseek-chat`, `deepseek-reasoner`) zodra `DEEPSEEK_API_KEY` aanwezig is.
- `LLMProviderFactory._detect_provider_type()` gedrag is vastgelegd via nieuwe tests.
- Nieuwe unit- en architectuurtests die bovenstaande gedragen afdwingen.

### Out of scope

- Legacy `src/core/llm/llm_service.py` en `GuaranteedLLMService` vallen ook stil terug op mock in productie; dit is een pre-existing architectuur-issue dat naar Rakesh is geescaleerd.
- Echte end-to-end LLM-call met DeepSeek (dag 5, sidebar-aansluiting).
- Prometheus-metrics voor LLM-failover.
- UI-wijzigingen.

---

## Build summary

- Nieuw: `tests/unit/services/llm/test_no_mock_in_production.py`
- Nieuw: `tests/unit/llm/test_provider_factory_deepseek.py`
- Nieuw: `tests/unit/copilot/test_fallback_chain_enabled.py`
- Nieuw: `tests/architecture/test_prod_compose_has_llm_config.py`
- Gewijzigd: `src/core/services/llm/service.py` (productie-guard)
- Gewijzigd: `src/core/services/llm/factory.py` (`DEFAULT_LLM_MODEL` / `LLM_MODEL` lezen)
- Gewijzigd: `src/core/llm/fallback_chain.py` (DeepSeek-registratie + `_call_deepseek` branch)
- Gewijzigd: `docker-compose.prod.yml` (LLM env vars voor backend en learning-worker)
- Verifieerd ongewijzigd: `src/core/llm/provider_factory.py` (DeepSeek-detectie werkt)
- Verifieerd ongewijzigd: `src/core/config/config_validator.py` en `src/core/shared/config.py` (productie vereist echte LLM-key)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-LLM-001a | LLMService productie-guard | Service | `src/core/services/llm/service.py` | Wijziging | LLM initialisatie flow |
| BE-LLM-001b | ProviderFactory env-model fallback | Utility | `src/core/services/llm/factory.py` | Wijziging | LLM initialisatie flow |
| BE-LLM-001c | Productie LLM-config in compose | Config | `docker-compose.prod.yml` | Wijziging | Deploy / startup flow |
| BE-LLM-001d | DeepSeek-registratie in fallback chain | Utility | `src/core/llm/fallback_chain.py` | Wijziging | LLM failover flow |
| BE-LLM-001e | DeepSeek-detectie tests | Test | `tests/unit/llm/test_provider_factory_deepseek.py` | Nieuw | LLM initialisatie flow |
| BE-LLM-001f | No-mock-in-productie tests | Test | `tests/unit/services/llm/test_no_mock_in_production.py` | Nieuw | LLM initialisatie flow |
| BE-LLM-001g | Failover-chain tests | Test | `tests/unit/copilot/test_fallback_chain_enabled.py` | Nieuw | LLM failover flow |
| BE-LLM-001h | Prod-compose architectuurtest | Test | `tests/architecture/test_prod_compose_has_llm_config.py` | Nieuw | Deploy / startup flow |

---

## API-flows

### Flow 1: LLMService initialisatie

- Naam: LLMService opstarten met configuratie
- Trigger: `LLMService(...)` instantiatie
- Voorwaarden: omgevingsvariabelen `ENVIRONMENT`, `LLM_PROVIDER`, `LLM_MODEL` / `DEFAULT_LLM_MODEL`, provider-specifieke API-key
- Request-pad: caller -> `LLMService.__init__` -> `ProviderFactory.create` of `ProviderFactory.create_from_env`
- Service-stappen:
  1. Bij expliciete `provider` + `model`: `ProviderFactory.create(...)`.
  2. Anders: `ProviderFactory.create_from_env(...)` leest `LLM_PROVIDER`, `DEFAULT_LLM_MODEL`, `LLM_MODEL`, temperatuur, tokens, timeout, API-key.
  3. Bij `ValueError` (onbekende provider of ontbrekend model):
     - Productie: log error en re-raise; geen mock.
     - Dev/test: log warning en val terug op `MockProvider`.
  4. Post-constructie: als `is_production()` en `provider_name == "mock"`, raise `RuntimeError`.
- DB-operaties: geen
- Successtatus: `LLMService` instantie met geldige provider
- Foutpaden:
  - `ValueError`: ongeldige provider of ontbrekend model
  - `RuntimeError`: mock provider in productie
- Eindtoestand: provider is geconfigureerd; bij productie nooit mock

### Flow 2: LLM failover chain

- Naam: LLM call met tiered fallback
- Trigger: `await get_fallback_chain().generate(...)`
- Voorwaarden: `DEEPSEEK_API_KEY` (of `GOOGLE_API_KEY` / `OPENAI_API_KEY`) geregistreerd
- Request-pad: caller -> `LLMFallbackChain.generate()` -> `_call_model()` per tier
- Service-stappen:
  1. `get_fallback_chain()` bouwt singleton-chain.
  2. Als `DEEPSEEK_API_KEY` aanwezig: registreer `deepseek-chat` (PRIMARY) en `deepseek-reasoner` (SECONDARY).
  3. Loop over tiers PRIMARY -> SECONDARY -> LOCAL -> HEURISTIC.
  4. Per model: circuit-breaker check, call via `_call_deepseek`, `_call_google`, `_call_openai`, `_call_ollama` of `_call_lmstudio`.
  5. Bij succes: return `FallbackResult`.
  6. Bij falen: volgende model, tot `max_fallbacks` bereikt.
- DB-operaties: geen
- Successtatus: `FallbackResult(success=True, model_used=..., ...)`
- Foutpaden:
  - Alle providers falen: `FallbackResult(success=False, errors=[...])`
  - OPEN circuit: skip zonder attempt te verhogen
- Eindtoestand: antwoord of leeg resultaat met error-lijst

### Flow 3: Copilot fallback-provider wiring

- Naam: CopilotService fallback providers opbouwen
- Trigger: `_build_copilot_service()`
- Voorwaarden: `LLM_FALLBACK_PROVIDER` env var gezet (bijv. `gemini`)
- Request-pad: Copilot dependency -> `_build_fallback_providers(primary)`
- Service-stappen:
  1. Lees `LLM_FALLBACK_PROVIDER`.
  2. Indien leeg / `none` / `disabled`: return `[]`.
  3. Vraag provider aan `LLMProviderFactory`.
  4. Als fallback-type gelijk is aan primary-type: return `[]`.
  5. Anders return `[fallback]`.
- Successtatus: lijst met nul of een fallback provider
- Foutpaden: exception -> log warning, return `[]`

---

## Detaildocumentatie per artefact

---

## [BE-LLM-001a] LLMService productie-guard

### 1. Type
- Serviceklasse-wijziging

### 2. Locatie
- Bestandspad: `src/core/services/llm/service.py`
- Klasse / functie: `LLMService.__init__`

### 3. Gerelateerde flow
- LLMService initialisatie flow

### 4. Doel
Voorkomen dat productie stil terugvalt op een mock-LLM bij ontbrekende of ongeldige configuratie.

### 5. Functionele beschrijving
`LLMService` wordt geinitialiseerd via een expliciete provider/model-combinatie of via omgevingsvariabelen. In productie leidt elke mislukte configuratie tot een harde fout; buiten productie blijft het bestaande mock-fallback gedrag beschikbaar voor ontwikkeling en testen. Ook als een caller expliciet `provider="mock"` opgeeft, wordt dit in productie geweigerd.

### 6. Technische beschrijving
- Import `is_production` uit `src.core.shared.config`.
- `try/except ValueError` rond provider-creatie:
  - `is_production() == True`: `logger.error(..., exc_info=True)` en `raise`.
  - `is_production() == False`: `logger.warning(...)` en `self.provider = ProviderFactory.create("mock", "mock-model")`.
- Post-constructie-check:
  ```python
  if is_production() and self.provider.provider_name == "mock":
      raise RuntimeError("LLM provider resolved to MockProvider in production. ...")
  ```

### 7. Zichtbaarheids- en toegangsregels
- Intern platform-service; geen HTTP endpoint.
- Geen tenant-afhankelijke autorisatie op dit niveau.
- Feature flag: geen; gedrag hangt af van `ENVIRONMENT`.

### 8. Request-specificatie
- Handtekening ongewijzigd:
  ```python
  def __init__(self, provider=None, model=None, max_retries=3, token_budget=None, enable_cache=True, **provider_config)
  ```

### 9. Response-specificatie
- Succes: `LLMService` instantie.
- Fout:
  - `ValueError`: ongeldige provider/model in productie.
  - `RuntimeError`: mock provider opgelost in productie.

### 10. Validaties en constraints
- `is_production()` is de enige bron van waarheid voor productie-detectie.
- `provider_name` moet een string-attribuut zijn op provider-instantie.

### 11. Business rules
- Mock-fallback is toegestaan buiten productie.
- Mock-fallback is verboden in productie.
- Expliciete mock-aanvraag in productie faalt.

### 12. Afhankelijkheden
- `src.core.services.llm.factory.ProviderFactory`
- `src.core.shared.config.is_production`
- `src.core.services.llm.providers.MockProvider`

### 13. Foutafhandeling
- `ValueError` bij ontbrekend model: raise in productie, mock fallback elders.
- `RuntimeError` bij mock-provider in productie.

### 14. Transacties en data-integriteit
- Geen DB-operaties.

### 15. Telemetry / logging / tracing
- `logger.error` bij productie-configuratiefout.
- `logger.warning` bij dev/test mock-fallback.
- `logger.info` bij succesvolle initialisatie.

### 16. Caching
- Niet van toepassing op initialisatie.

### 17. Acceptatiecriteria
- Productie + ontbrekende config -> `LLMService()` raise.
- Dev/test + ontbrekende config -> `LLMService()` valt terug op `MockProvider`.
- Productie + expliciet mock -> `LLMService()` raise `RuntimeError`.

### 18. Integratoruitleg
- Gebruik `LLMService()` zonder argumenten in productie alleen als alle verplichte LLM-env vars zijn gezet.
- Deploy faalt hard zonder `DEEPSEEK_API_KEY` of alternatieve key.

### 19. Trainingssamenvatting
- Actor: backend service die `LLMService` initialiseert
- Voorwaarde: `ENVIRONMENT=production` en ontbrekende/ongeldige LLM-config
- Actie: `LLMService()`
- Systeemverwerking: provider-creatie faalt -> guard raise
- Succesrespons: `LLMService` met echte provider
- Foutrespons: `RuntimeError` of `ValueError`
- Uitzonderingen: dev/test mag mock gebruiken

---

## [BE-LLM-001b] ProviderFactory env-model fallback

### 1. Type
- Utility-wijziging

### 2. Locatie
- Bestandspad: `src/core/services/llm/factory.py`
- Klasse / functie: `ProviderFactory.create_from_env`

### 3. Gerelateerde flow
- LLMService initialisatie flow

### 4. Doel
Zorgen dat zowel `LLM_MODEL` als `DEFAULT_LLM_MODEL` als modelbron kunnen dienen, zodat de service-laag en de legacy `LLMProviderFactory` allebei correct worden gevoed.

### 5. Functionele beschrijving
`create_from_env` leest nu:
```python
model = model or os.getenv("DEFAULT_LLM_MODEL") or os.getenv("LLM_MODEL")
```
Dit maakt de factory compatibel met de variable naam die de rest van de codebase gebruikt (`DEFAULT_LLM_MODEL`) en met `LLM_MODEL`.

### 6. Technische beschrijving
- Wijziging op regel 166 van `factory.py`.
- Blijft `ValueError` raisen als geen model bekend is (behalve expliciete mock).

### 7. Zichtbaarheids- en toegangsregels
- Interne factory.

### 8. Request-specificatie
- Handtekening ongewijzigd.

### 9. Response-specificatie
- `LLMProvider` instantie.

### 10. Validaties en constraints
- Model moet via argument of env var beschikbaar zijn.

### 11. Business rules
- `DEFAULT_LLM_MODEL` heeft voorrang boven `LLM_MODEL`.

### 12. Afhankelijkheden
- `os` module.

### 13. Foutafhandeling
- `ValueError` bij ontbrekend model.

### 14. Transacties en data-integriteit
- Geen.

### 15. Telemetry / logging / tracing
- Geen extra logging.

### 16. Caching
- Nee.

### 17. Acceptatiecriteria
- `LLMService()` werkt met `DEFAULT_LLM_MODEL` gezet.
- `LLMService()` werkt met `LLM_MODEL` gezet.

### 18. Integratoruitleg
- Zet in productie `DEFAULT_LLM_MODEL` (bijv. `deepseek-chat`) of `LLM_MODEL`.

### 19. Trainingssamenvatting
- Actor: deployer / ontwikkelaar
- Voorwaarde: `LLM_PROVIDER` gezet
- Actie: `LLMService()` initialiseren
- Systeemverwerking: factory leest model uit env
- Succesrespons: geldige provider
- Foutrespons: `ValueError` bij ontbrekend model
- Uitzonderingen: mock kan fallback zijn buiten productie

---

## [BE-LLM-001c] Productie LLM-config in compose

### 1. Type
- Configuratie (Docker Compose)

### 2. Locatie
- Bestandspad: `docker-compose.prod.yml`
- Service environment-blokken: `backend`, `learning-worker`

### 3. Gerelateerde flow
- Deploy / startup flow

### 4. Doel
Zorgen dat productie-deploys expliciet LLM-provider, model en API-keys vereisen, gesourced uit env of Key Vault, nooit plaintext in het compose-bestand.

### 5. Functionele beschrijving
Beide services krijgen de volgende omgevingsvariabelen:
- `LLM_PROVIDER=${LLM_PROVIDER:?...}` (verplicht)
- `DEFAULT_LLM_MODEL=${DEFAULT_LLM_MODEL:?...}` (verplicht)
- `LLM_MODEL=${DEFAULT_LLM_MODEL:?...}` (verplicht)
- `DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:?...}` (verplicht)
- `LLM_FALLBACK_PROVIDER=${LLM_FALLBACK_PROVIDER:-gemini}` (optioneel, default gemini)
- `GEMINI_API_KEY=${GEMINI_API_KEY:-}` (optioneel)

### 6. Technische beschrijving
- `${VAR:?melding}` zorgt dat `docker compose` hard faalt als de variabele ontbreekt.
- Geen hardcoded API-keys; waarden beginnen altijd met `${`.

### 7. Zichtbaarheids- en toegangsregels
- Alleen relevant voor productie-deploy.

### 8. Request-specificatie
- Niet van toepassing (infrastructuur).

### 9. Response-specificatie
- Niet van toepassing.

### 10. Validaties en constraints
- `DEEPSEEK_API_KEY` is verplicht gesteld in productie.
- `LLM_FALLBACK_PROVIDER` mag `none` zijn om fallback uit te schakelen.

### 11. Business rules
- Secrets komen nooit in Git.
- Deploy zonder verplichte key faalt voor opstarten.

### 12. Afhankelijkheden
- Externe secret store / CI/CD.

### 13. Foutafhandeling
- `docker compose` geeft fout bij ontbrekende verplichte variabele.

### 14. Transacties en data-integriteit
- Geen.

### 15. Telemetry / logging / tracing
- Geen.

### 16. Caching
- Nee.

### 17. Acceptatiecriteria
- `docker-compose.prod.yml` bevat de zes vereiste LLM-variabelen in `backend` en `learning-worker`.
- Elke waarde is een `${...}` substitutie.
- Geen hardcoded `sk-` strings.

### 18. Integratoruitleg
- Vul in productie `LLM_PROVIDER`, `DEFAULT_LLM_MODEL` en `DEEPSEEK_API_KEY` via Azure Key Vault of CI-secret-store.
- Optioneel: zet `LLM_FALLBACK_PROVIDER=gemini` en `GEMINI_API_KEY`.

### 19. Trainingssamenvatting
- Actor: DevOps / deployer
- Voorwaarde: productie stack opstarten
- Actie: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`
- Systeemverwerking: compose valideert verplichte LLM-env vars
- Succesrespons: containers starten
- Foutrespons: compose error bij ontbrekende key
- Uitzonderingen: fallback provider mag ontbrekende key hebben als primary werkt

---

## [BE-LLM-001d] DeepSeek-registratie in fallback chain

### 1. Type
- Utility-wijziging

### 2. Locatie
- Bestandspad: `src/core/llm/fallback_chain.py`
- Klasse / functie: `get_fallback_chain`, `LLMFallbackChain._call_model`, `LLMFallbackChain._call_deepseek`

### 3. Gerelateerde flow
- LLM failover flow

### 4. Doel
DeepSeek als volwaardige provider in de app-brede failover-chain beschikbaar maken, met actuele model-id's.

### 5. Functionele beschrijving
Als `DEEPSEEK_API_KEY` aanwezig is, registreert `get_fallback_chain()`:
- `deepseek-chat` als PRIMARY model
- `deepseek-reasoner` als SECONDARY model

`_call_model` routeert `provider == "deepseek"` naar `_call_deepseek`, die een OpenAI-compatibele chat-completions call doet naar `https://api.deepseek.com/chat/completions`.

### 6. Technische beschrijving
- `get_fallback_chain()` controleert `os.getenv("DEEPSEEK_API_KEY")` en registreert twee `ModelConfig` entries.
- `_call_deepseek` gebruikt `httpx.AsyncClient` met `Authorization: Bearer <key>`.
- Ondersteunt `response_format: {"type": "json_object"}` als `response_model` en `supports_json_mode=True`.

### 7. Zichtbaarheids- en toegangsregels
- Intern platform-gebruik.

### 8. Request-specificatie
- `LLMFallbackChain.generate(prompt=..., response_model=..., ...)`

### 9. Response-specificatie
- `FallbackResult` met `model_used` en `tier_used`.

### 10. Validaties en constraints
- Vereist `DEEPSEEK_API_KEY` om te registreren.
- Vereist geldige API-key om te callen.

### 11. Business rules
- Geen verouderde placeholder-modelnamen (`deepseek-v1`, `deepseek-v2`, etc.) in de chain.
- DeepSeek-modellen moeten in PRIMARY of SECONDARY tier zitten.

### 12. Afhankelijkheden
- `httpx`
- `src.core.resilience.circuit_breaker.CircuitBreakerRegistry`

### 13. Foutafhandeling
- `ValueError` bij ontbrekende key.
- `httpx.HTTPStatusError` bij API-fouten -> valt terug naar volgende model.

### 14. Transacties en data-integriteit
- Geen.

### 15. Telemetry / logging / tracing
- `logger.info` bij registratie van model.
- `logger.warning` bij model-falen in chain.

### 16. Caching
- Nee.

### 17. Acceptatiecriteria
- `get_fallback_chain()` registreert `deepseek-chat` en `deepseek-reasoner` bij aanwezige key.
- Geen stale placeholders in geregistreerde modellen.
- `_call_model` delegeert deepseek naar `_call_deepseek`.

### 18. Integratoruitleg
- Zet `DEEPSEEK_API_KEY` om DeepSeek in de failover-chain te activeren.
- De chain probeert automatisch `deepseek-chat`, daarna `deepseek-reasoner`, daarna fallback/providers.

### 19. Trainingssamenvatting
- Actor: platform service die `get_fallback_chain().generate()` aanroept
- Voorwaarde: `DEEPSEEK_API_KEY` gezet
- Actie: `await get_fallback_chain().generate(prompt=...)`
- Systeemverwerking: registreer DeepSeek-modellen, probeer primary, fallback bij falen
- Succesrespons: `FallbackResult(success=True, model_used="deepseek-chat")`
- Foutrespons: `FallbackResult(success=False, errors=[...])`
- Uitzonderingen: circuit OPEN -> skip zonder attempt

---

## Integratorhandleiding

### Voor DevOps / deployers

- Zorg dat de productie secret-store de volgende variabelen bevat:
  - `LLM_PROVIDER=deepseek`
  - `DEFAULT_LLM_MODEL=deepseek-chat`
  - `DEEPSEEK_API_KEY=<key>`
  - Optioneel: `LLM_FALLBACK_PROVIDER=gemini` + `GEMINI_API_KEY=<key>`
- Commit nooit API-keys; compose gebruikt uitsluitend `${VAR}`-referenties.
- Een deploy zonder `DEEPSEEK_API_KEY` faalt al tijdens `docker compose up`.

### Voor ontwikkelaars

- In dev/test mag `LLMService()` nog steeds terugvallen op `MockProvider` als er geen key is.
- Testen kunnen `is_production` mocken om het productie-gedrag te verifieren.

---

## Open aannames

- DeepSeek is de beoogde primaire provider in productie.
- `DEEPSEEK_API_KEY` wordt altijd via env/Key Vault geleverd, nooit hardcoded.
- `is_production()` is de enige bron van waarheid voor productie-detectie.

## Open vragen

- Moet de legacy `src/core/llm/llm_service.py` en `GuaranteedLLMService` ook een productie-guard krijgen? (Pre-existing, geescaleerd naar Rakesh.)

## Risico's

- **Legacy mock-fallback**: oudere `LLMService` in `src/core/llm/` valt nog steeds stil terug op mock in productie. Dit is buiten scope van deze dag maar kan leiden tot stille degradatie als die paden nog worden gebruikt.
- **DSM006 pre-existing failure**: architectuurtest `test_dsm006_ar_governance_fan_out.py` faalt door een extra import (`tenant_service -> governance.models`) die niet door deze wijzigingen is geintroduceerd.
- **Echte LLM-call niet getest**: deze dag test alleen configuratie en wiring; een echte DeepSeek-call volgt op dag 5.

---

## QA-checks

- [x] 8/8 doeltests PASS
- [x] Regressiecheck: 892 passed, 1 pre-existing failure (DSM006)
- [x] `ruff check` op gewijzigde bestanden: 0 errors
- [x] `pyright` op gewijzigde bestanden: 0 errors
- [x] Geen hardcoded secrets in compose
- [x] ASCII-only in nieuwe code/comments

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Alle relevante foutstatussen beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig per artefact
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED WITH MINOR GAPS
