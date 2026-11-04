# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-010
- Feature naam: DeepSeekClient & OllamaClient complete_json() Implementatie
- Status: APPROVED WITH MINOR GAPS
- Auteur: Rakesh Ramkhelawan
- Reviewer: reviewer-prompt (SP-H06 review)
- Datum: 2026-05-30
- Gerelateerde user story / ticket: B-025 (SP-H06)
- Gerelateerde router / module: src/core/llm/llm_client.py
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.1

---

## Doel en scope

### Doel

`DeepSeekClient` miste een eigen `complete_json()` methode. `OllamaClient.complete_json()` retourneerde direct `success=False` zonder een JSON-mode-poging, waardoor de LLM-failoverchain (ADR-026) hard crashte bij elke poging om JSON-structured output via deze clients te produceren. Deze feature implementeert werkende JSON-mode completions voor beide clients conform het bestaande delegatiepatroon uit `DeepSeekProvider` en `OllamaProvider`.

### In scope

- `DeepSeekClient.complete_json()` toegevoegd in `llm_client.py`
- `DeepSeekClient.chat_completion()` uitgebreid: `response_format` kwarg wordt opgenomen in het HTTP-payload
- `OllamaClient.complete_json()` vervangen: oude stub die altijd `success=False` retourneerde, vervangen door delegatie aan `chat_completion()` met `format="json"`
- `OllamaClient.chat_completion()` uitgebreid: `format` kwarg wordt opgenomen in het `/api/generate` payload
- 6 unit tests in `tests/unit/test_sp_h06_deepseek_complete_json.py`

### Out of scope

- Migratie van `OllamaClient` naar het `/api/chat` endpoint (dat is `OllamaProvider`; buiten scope B-025)
- Aanpassingen aan `DeepSeekProvider` of `OllamaProvider` (die hadden al werkende implementaties)
- Schema-validatie van de JSON-output door de client zelf
- Streaming JSON-completions

---

## Build summary

- Nieuw gebouwd: `DeepSeekClient.complete_json()` methode; `tests/unit/test_sp_h06_deepseek_complete_json.py` (6 tests)
- Gewijzigd: `OllamaClient.complete_json()` (stub vervangen door werkende implementatie); `DeepSeekClient.chat_completion()` (response_format payload-inclusie); `OllamaClient.chat_completion()` (format payload-inclusie)
- Verwijderd: Oude `OllamaClient.complete_json()` stub die altijd `success=False` retourneerde
- Beinvloede bestaande flows: LLM-failoverchain (ADR-026) -- DeepSeek- en Ollama-posities in de keten kunnen nu JSON-mode completions leveren zonder hard te falen

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SVC-010a | DeepSeekClient.complete_json() | Service-methode | src/core/llm/llm_client.py | Nieuw | LLM JSON-mode completion via failoverchain |
| BE-SVC-010b | DeepSeekClient.chat_completion() | Service-methode | src/core/llm/llm_client.py | Wijziging | LLM JSON-mode completion via failoverchain |
| BE-SVC-010c | OllamaClient.complete_json() | Service-methode | src/core/llm/llm_client.py | Wijziging (stub vervangen) | LLM JSON-mode completion via failoverchain |
| BE-SVC-010d | OllamaClient.chat_completion() | Service-methode | src/core/llm/llm_client.py | Wijziging | LLM JSON-mode completion via failoverchain |

---

## API-flows

n.v.t. -- utility klasse zonder HTTP-endpoints. De flows hieronder beschrijven interne aanroepketens, niet HTTP-routes.

### Flow BE-SVC-010-F1: DeepSeek JSON-mode completion

- Naam: complete_json() via DeepSeekClient
- Trigger (HTTP-methode + route of event): Interne aanroep -- `client.complete_json(messages, schema=MySchema)` vanuit `LLMHandler`, `CopilotService` of `FocusBuilderService`
- Voorwaarden (auth, tenant, feature flag): DeepSeek is de geconfigureerde LLM-provider; `httpx` package beschikbaar; `DEEPSEEK_API_KEY` aanwezig in env
- Request-pad: caller -> `DeepSeekClient.complete_json()` -> `DeepSeekClient.chat_completion()` -> HTTPS POST `https://api.deepseek.com/chat/completions`
- Service-stappen: (1) `kwargs.setdefault("response_format", {"type": "json_object"})` -- stelt JSON-mode in als de caller geen eigen format meegaf; (2) delegeert aan `chat_completion(messages, **kwargs)`; (3) `chat_completion()` bouwt payload inclusief `response_format`; (4) POST naar DeepSeek API; (5) retourneert `LLMResponse`
- DB-operaties: geen
- Successtatus + response: `LLMResponse(success=True, content='{"...": "..."}', model=..., provider=..., usage={...}, response_time=...)`
- Foutpaden: HTTP-statuscode != 200 -> `LLMResponse(success=False, error_message="HTTP <code>: <body>")`; exception (timeout, netwerkfout) -> `LLMResponse(success=False, error_message=str(e))`; `httpx` niet beschikbaar -> `LLMResponse(success=False, error_message="DeepSeek client not initialized")`
- Eindtoestand (DB, cache, events): geen DB-wijziging; interne metrieken bijgewerkt via `_update_metrics(response_time, success)`

### Flow BE-SVC-010-F2: Ollama JSON-mode completion

- Naam: complete_json() via OllamaClient
- Trigger (HTTP-methode + route of event): Interne aanroep -- `client.complete_json(messages, schema=MySchema)` vanuit `LLMHandler`, `CopilotService` of `FocusBuilderService`
- Voorwaarden (auth, tenant, feature flag): Ollama is de geconfigureerde LLM-provider (OllamaClient); Ollama-server bereikbaar op geconfigureerd adres; `aiohttp` package beschikbaar
- Request-pad: caller -> `OllamaClient.complete_json()` -> `OllamaClient.chat_completion()` -> HTTP POST `{OLLAMA_BASE_URL}/api/generate`
- Service-stappen: (1) `kwargs.setdefault("format", "json")` -- stelt JSON-mode in als de caller geen eigen format meegaf; (2) delegeert aan `chat_completion(messages, **kwargs)`; (3) `chat_completion()` bouwt payload inclusief `"format": "json"`; (4) POST naar Ollama `/api/generate`; (5) retourneert `LLMResponse`
- DB-operaties: geen
- Successtatus + response: `LLMResponse(success=True, content='{"...": "..."}', model=..., provider=..., response_time=...)`
- Foutpaden: HTTP-statuscode != 200 -> `LLMResponse(success=False, error_message="HTTP <code>: ...")`; exception (timeout, Ollama niet bereikbaar) -> `LLMResponse(success=False, error_message=str(e))`
- Eindtoestand (DB, cache, events): geen DB-wijziging; interne metrieken bijgewerkt via `_update_metrics(response_time, success)`

---

## Detaildocumentatie per artefact

---

## [BE-SVC-010a] DeepSeekClient.complete_json()

### 1. Type

- Service-methode (utility -- geen HTTP-endpoint)

### 2. Locatie

- Bestandspad: src/core/llm/llm_client.py
- Klasse / functie: `DeepSeekClient.complete_json()`

### 3. Gerelateerde flow

- BE-SVC-010-F1 (DeepSeek JSON-mode completion)

### 4. Doel

- Biedt een werkende JSON-mode completion voor `DeepSeekClient`. Zonder deze methode viel de failoverchain terug op de base-class `NotImplementedError`, wat de volledige pipeline blokkeerde wanneer DeepSeek een positie in de keten innam.

### 5. Functionele beschrijving

- Accepteert een lijst van `LLMMessage`-objecten en een schema-type. Zorgt ervoor dat de DeepSeek API wordt gevraagd om JSON-gestructureerde output door `response_format: {"type": "json_object"}` toe te voegen aan de aanroep. Retourneert een `LLMResponse` met de JSON-string in `content`.
- Als de caller zelf een `response_format` kwarg meegeeft, wordt die niet overschreven (`setdefault`).

### 6. Technische beschrijving

- Methode-signatuur: `async def complete_json(self, messages: list[LLMMessage], schema: type[Any], **kwargs: Any) -> LLMResponse`
- Implementatie: `kwargs.setdefault("response_format", {"type": "json_object"})` gevolgd door `return await self.chat_completion(messages, **kwargs)`
- `chat_completion()` neemt `response_format` op in het HTTP-payload als de kwarg aanwezig is: `if kwargs.get("response_format"): payload["response_format"] = kwargs["response_format"]`
- HTTP-endpoint: `POST https://api.deepseek.com/chat/completions` (OpenAI-compatibel)
- Auth: `Authorization: Bearer {DEEPSEEK_API_KEY}` header
- Geen eigen retrylogica -- retries worden afgehandeld door de failoverchain (ADR-026)
- Schema-parameter wordt doorgegeven maar niet gebruikt door de client zelf; validatie is verantwoordelijkheid van de caller (bijv. `model_validate_json(raw.content)`)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. -- interne service-methode, niet via HTTP blootgesteld
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: n.v.t. -- de client is stateless; tenant-context bevindt zich in de aanroepende service
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: n.v.t. -- utility klasse zonder HTTP-endpoints
- Route: n.v.t. -- utility klasse zonder HTTP-endpoints
- Path parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Query parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Request body (schema): n.v.t. -- utility klasse zonder HTTP-endpoints
- Verplichte headers: n.v.t. -- utility klasse zonder HTTP-endpoints

### 9. Response-specificatie

- Successtatus: n.v.t. -- utility klasse zonder HTTP-endpoints; methode retourneert `LLMResponse(success=True, content=<json_string>, ...)`
- Response schema: `LLMResponse` dataclass met velden: `content: str`, `model: str`, `provider: str`, `success: bool`, `error_message: str | None`, `usage: dict`, `response_time: float`
- Foutstatussen: n.v.t. -- utility klasse zonder HTTP-endpoints; foutcondities worden uitgedrukt in `LLMResponse(success=False, error_message=...)`

### 10. Validaties en constraints

- `messages` moet een niet-lege lijst zijn van `LLMMessage`-objecten
- `schema` wordt doorgegeven maar niet geinspecteerd door de client; caller is verantwoordelijk voor `model_validate_json()`
- `response_format` kwarg wordt niet overschreven als de caller hem zelf meegaf

### 11. Business rules

- JSON-mode wordt ingesteld via `response_format: {"type": "json_object"}` conform de OpenAI-compatible DeepSeek API
- De client garandeert niet dat de output valide JSON is; dat is de verantwoordelijkheid van de caller (zie SP-H03 valkuil: altijd `raw.success` checken voor `model_validate_json()`)
- Caller-gespecificeerde `response_format` heeft prioriteit boven de default (setdefault-semantiek)

### 12. Afhankelijkheden

- `httpx` package (deferred import in `__init__`); als niet aanwezig: `_available=False` en methode retourneert direct `success=False`
- `DeepSeekClient.chat_completion()` -- delegatiedoel
- `DEEPSEEK_API_KEY` environment variable

### 13. Foutafhandeling

- 400: n.v.t. (geen HTTP-endpoint); equivalent: `LLMResponse(success=False, error_message="HTTP 400: ...")` bij DeepSeek API-fout
- 401: n.v.t.; equivalent: `LLMResponse(success=False, error_message="HTTP 401: ...")` bij ongeldige API-sleutel
- 403: n.v.t.
- 404: n.v.t.
- 409: n.v.t.
- 422: n.v.t.
- 429: n.v.t.; equivalent: `LLMResponse(success=False, error_message="HTTP 429: ...")` bij rate limit; failoverchain schakelt over naar volgende provider
- 500: n.v.t.; equivalent: `LLMResponse(success=False, error_message="HTTP 500: ...")` bij DeepSeek serverfout
- 503: n.v.t.; equivalent: `LLMResponse(success=False, error_message=str(e))` bij netwerkfout of timeout

### 14. Transacties en dataIntegriteit

- Geen database-operaties; geen transacties

### 15. Telemetry / logging / tracing

- `_update_metrics(response_time, success)` wordt aangeroepen via `chat_completion()` na elke poging
- Falen wordt gelogd via `logger.error(f"DeepSeek chat completion failed: {e}")` in `chat_completion()`
- Geen expliciete OpenTelemetry spans op methode-niveau; tracing is verantwoordelijkheid van de aanroepende service

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- `DeepSeekClient` heeft een eigen `complete_json()` methode in `__dict__` (niet geerfed van base class)
- Aanroep van `complete_json()` zonder `response_format` kwarg resulteert in `kwargs["response_format"] == {"type": "json_object"}` bij de delegatie aan `chat_completion()`
- `chat_completion()` neemt `response_format` op in het HTTP-payload als de kwarg aanwezig is
- Als de caller `response_format` zelf meegeeft, wordt die waarde niet overschreven door `setdefault`
- Bij succesvolle DeepSeek API-response retourneert `complete_json()` `LLMResponse(success=True)` met JSON-string in `content`
- Bij HTTP-fout van DeepSeek API retourneert `complete_json()` `LLMResponse(success=False)` met foutbericht in `error_message`

### 18. Integratoruitleg

- n.v.t. -- utility klasse zonder HTTP-endpoints; onderstaande uitleg is voor interne callers (services, agents)
- Aanroep: `response = await client.complete_json(messages, schema=MijnSchema)` -- de client regelt JSON-mode automatisch
- Controleer altijd `response.success` voor `model_validate_json(response.content)` (zie CLAUDE.md SP-H03 valkuil)
- Om een ander response-format af te dwingen: geef `response_format={"type": "..."}` mee als kwarg -- de client overschrijft dit niet
- `OllamaProvider` verdient de voorkeur boven `OllamaClient` voor productie-JSON-mode (betere message semantics via `/api/chat`)

### 19. Trainingssamenvatting

Flow 1: complete_json() via DeepSeekClient

- Actor: CopilotService of FocusBuilderService (interne aanroeper in de LLM-failoverchain)
- Voorwaarde: DeepSeek is de geconfigureerde of geselecteerde LLM-provider; `httpx` beschikbaar; `DEEPSEEK_API_KEY` aanwezig
- Actie (request): `await client.complete_json(messages, schema=CopilotAction)`
- Systeemverwerking: `setdefault("response_format", {"type": "json_object"})` wordt toegepast; gedelegeerd aan `chat_completion()`; HTTP POST naar `https://api.deepseek.com/chat/completions` met `response_format` in payload
- Succesrespons: `LLMResponse(success=True, content='{"action": "...", ...}', model=..., provider=..., usage={...})`
- Foutrespons: `LLMResponse(success=False, error_message="HTTP 429: rate limit exceeded")` of `LLMResponse(success=False, error_message="Connection timeout")`
- Uitzonderingen: Caller-gespecificeerde `response_format` overschrijft de default niet (setdefault-semantiek); schema-validatie is verantwoordelijkheid van de caller

---

## [BE-SVC-010b] DeepSeekClient.chat_completion() -- response_format payload-inclusie

### 1. Type

- Service-methode (utility -- geen HTTP-endpoint)

### 2. Locatie

- Bestandspad: src/core/llm/llm_client.py
- Klasse / functie: `DeepSeekClient.chat_completion()`

### 3. Gerelateerde flow

- BE-SVC-010-F1 (DeepSeek JSON-mode completion)

### 4. Doel

- Uitbreiden van de bestaande `chat_completion()` met de mogelijkheid om `response_format` in het HTTP-payload op te nemen. Zonder deze uitbreiding had `complete_json()` wel de kwarg ingesteld, maar werd die kwarg nooit naar de DeepSeek API doorgestuurd.

### 5. Functionele beschrijving

- Als `response_format` aanwezig is in kwargs, wordt die waarde opgenomen in het JSON-payload van het HTTP-verzoek aan DeepSeek. Dit instrueert de DeepSeek API om JSON-gestructureerde output te produceren.

### 6. Technische beschrijving

- Toevoeging in payload-bouwstap: `if kwargs.get("response_format"): payload["response_format"] = kwargs["response_format"]`
- Payload wordt uitgebreid na de basisvelden (`model`, `messages`, `max_tokens`, `temperature`, `stream`)
- Geen andere wijzigingen aan de methode-logica

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t.
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: n.v.t.
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: n.v.t. -- utility klasse zonder HTTP-endpoints
- Route: n.v.t. -- utility klasse zonder HTTP-endpoints
- Path parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Query parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Request body (schema): n.v.t. -- utility klasse zonder HTTP-endpoints
- Verplichte headers: n.v.t. -- utility klasse zonder HTTP-endpoints

### 9. Response-specificatie

- Successtatus: n.v.t. -- utility klasse zonder HTTP-endpoints
- Response schema: `LLMResponse` (zie BE-SVC-010a sectie 9)
- Foutstatussen: n.v.t. -- utility klasse zonder HTTP-endpoints

### 10. Validaties en constraints

- `response_format` wordt opgenomen als de kwarg een truthy waarde heeft; `None` of lege dict worden niet opgenomen

### 11. Business rules

- Conformiteit aan de OpenAI-compatible DeepSeek API: `response_format` wordt ongewijzigd doorgegeven; de client normaliseert de waarde niet

### 12. Afhankelijkheden

- `httpx` (deferred import)
- DeepSeek API op `https://api.deepseek.com/chat/completions`

### 13. Foutafhandeling

- Identiek aan BE-SVC-010a sectie 13; geen aanvullende foutpaden door de uitbreiding

### 14. Transacties en dataIntegriteit

- Geen database-operaties

### 15. Telemetry / logging / tracing

- Identiek aan BE-SVC-010a sectie 15

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- Als `response_format` aanwezig is in kwargs, bevat het HTTP-payload de sleutel `response_format` met de opgegeven waarde
- Als `response_format` niet aanwezig is in kwargs, bevat het HTTP-payload de sleutel `response_format` niet

### 18. Integratoruitleg

- n.v.t. -- utility klasse zonder HTTP-endpoints; interne callers hoeven geen actie te ondernemen; de uitbreiding is transparant

### 19. Trainingssamenvatting

Flow: response_format wordt opgenomen in het DeepSeek HTTP-payload

- Actor: `DeepSeekClient.complete_json()` (interne aanroeper)
- Voorwaarde: `kwargs["response_format"]` is aanwezig en truthy na `setdefault` in `complete_json()`
- Actie (request): `await self.chat_completion(messages, response_format={"type": "json_object"})`
- Systeemverwerking: payload-bouwstap voegt `"response_format": {"type": "json_object"}` toe; POST naar DeepSeek API
- Succesrespons: DeepSeek retourneert JSON-gestructureerde content; `LLMResponse(success=True, content=<json>)`
- Foutrespons: DeepSeek retourneert HTTP 4xx/5xx; `LLMResponse(success=False, error_message="HTTP <code>: ...")`
- Uitzonderingen: geen `response_format` in kwargs -> sleutel wordt niet toegevoegd aan payload

---

## [BE-SVC-010c] OllamaClient.complete_json() -- stub vervangen door werkende implementatie

### 1. Type

- Service-methode (utility -- geen HTTP-endpoint)

### 2. Locatie

- Bestandspad: src/core/llm/llm_client.py
- Klasse / functie: `OllamaClient.complete_json()`

### 3. Gerelateerde flow

- BE-SVC-010-F2 (Ollama JSON-mode completion)

### 4. Doel

- Vervangt de oude stub die altijd `LLMResponse(success=False, error_message="JSON completion not supported by OllamaClient")` retourneerde. De nieuwe implementatie delegeert aan `chat_completion()` met `format="json"`, waardoor Ollama een werkende JSON-mode completion kan leveren.

### 5. Functionele beschrijving

- Accepteert een lijst van `LLMMessage`-objecten en een schema-type. Zorgt ervoor dat Ollama in JSON-modus wordt aangestuurd door `format="json"` toe te voegen aan de aanroep. Retourneert een `LLMResponse` met de JSON-string in `content`.
- Als de caller zelf een `format` kwarg meegeeft, wordt die niet overschreven (`setdefault`).

### 6. Technische beschrijving

- Methode-signatuur: `async def complete_json(self, messages: list[LLMMessage], schema: type[Any], **kwargs: Any) -> LLMResponse`
- Implementatie: `kwargs.setdefault("format", "json")` gevolgd door `return await self.chat_completion(messages, **kwargs)`
- `chat_completion()` neemt `format` op in het HTTP-payload als de kwarg aanwezig is: `if kwargs.get("format"): payload["format"] = kwargs["format"]`
- HTTP-endpoint: `POST {OLLAMA_BASE_URL}/api/generate`
- Geen eigen retrylogica; retries worden afgehandeld door de failoverchain (ADR-026)
- Opmerking in docstring: `OllamaProvider` verdient de voorkeur voor productie-JSON-mode omdat die het `/api/chat` endpoint gebruikt met betere message semantics

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t.
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: n.v.t.
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: n.v.t. -- utility klasse zonder HTTP-endpoints
- Route: n.v.t. -- utility klasse zonder HTTP-endpoints
- Path parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Query parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Request body (schema): n.v.t. -- utility klasse zonder HTTP-endpoints
- Verplichte headers: n.v.t. -- utility klasse zonder HTTP-endpoints

### 9. Response-specificatie

- Successtatus: n.v.t. -- utility klasse zonder HTTP-endpoints; methode retourneert `LLMResponse(success=True, content=<json_string>, ...)`
- Response schema: `LLMResponse` (zie BE-SVC-010a sectie 9)
- Foutstatussen: n.v.t. -- utility klasse zonder HTTP-endpoints; foutcondities uitgedrukt in `LLMResponse(success=False, error_message=...)`

### 10. Validaties en constraints

- `messages` moet een niet-lege lijst zijn van `LLMMessage`-objecten
- Schema-parameter wordt doorgegeven maar niet geinspecteerd door de client
- `format` kwarg wordt niet overschreven als de caller hem zelf meegaf

### 11. Business rules

- JSON-mode wordt ingesteld via Ollama `format: "json"` parameter op het `/api/generate` endpoint
- De client garandeert niet dat de output valide JSON is; validatie is verantwoordelijkheid van de caller
- Voor productie wordt `OllamaProvider` aanbevolen boven `OllamaClient` voor JSON-completions

### 12. Afhankelijkheden

- `aiohttp` package; als niet aanwezig: client faalt bij initialisatie
- `OllamaClient.chat_completion()` -- delegatiedoel
- Ollama-server bereikbaar op geconfigureerd adres (`OLLAMA_BASE_URL`)

### 13. Foutafhandeling

- 400: n.v.t.; equivalent: `LLMResponse(success=False, error_message="HTTP 400: ...")` bij Ollama API-fout
- 401: n.v.t.
- 403: n.v.t.
- 404: n.v.t.; equivalent: `LLMResponse(success=False, error_message="HTTP 404: ...")` bij model niet gevonden
- 409: n.v.t.
- 422: n.v.t.
- 429: n.v.t.
- 500: n.v.t.; equivalent: `LLMResponse(success=False, error_message="HTTP 500: ...")` bij Ollama serverfout
- 503: n.v.t.; equivalent: `LLMResponse(success=False, error_message=str(e))` bij Ollama server niet bereikbaar

### 14. Transacties en dataIntegriteit

- Geen database-operaties; geen transacties

### 15. Telemetry / logging / tracing

- `_update_metrics(response_time, success)` wordt aangeroepen via `chat_completion()` na elke poging
- Identiek aan BE-SVC-010a sectie 15

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- `OllamaClient.complete_json()` gooit geen `NotImplementedError` meer
- Aanroep van `complete_json()` zonder `format` kwarg resulteert in `kwargs["format"] == "json"` bij de delegatie aan `chat_completion()`
- `chat_completion()` neemt `format` op in het HTTP-payload als de kwarg aanwezig is
- Als de caller `format` zelf meegeeft, wordt die waarde niet overschreven
- Bij succesvolle Ollama-response retourneert `complete_json()` `LLMResponse(success=True)` met JSON-string in `content`
- Bij onbereikbare Ollama-server retourneert `complete_json()` `LLMResponse(success=False)` met foutbericht

### 18. Integratoruitleg

- n.v.t. -- utility klasse zonder HTTP-endpoints; onderstaande uitleg is voor interne callers
- Aanroep identiek aan DeepSeekClient: `response = await client.complete_json(messages, schema=MijnSchema)`
- Controleer altijd `response.success` voor `model_validate_json(response.content)`
- Voor productie-gebruik verdient `OllamaProvider` de voorkeur (betere JSON-mode via `/api/chat`)

### 19. Trainingssamenvatting

Flow 2: complete_json() via OllamaClient

- Actor: CopilotService of FocusBuilderService (interne aanroeper in de LLM-failoverchain)
- Voorwaarde: Ollama is de geconfigureerde of geselecteerde LLM-provider (OllamaClient, niet OllamaProvider); Ollama-server bereikbaar
- Actie (request): `await client.complete_json(messages, schema=CopilotAction)`
- Systeemverwerking: `setdefault("format", "json")` wordt toegepast; gedelegeerd aan `chat_completion()`; HTTP POST naar `{OLLAMA_BASE_URL}/api/generate` met `"format": "json"` in payload
- Succesrespons: `LLMResponse(success=True, content='{"action": "...", ...}', model=..., provider=...)`
- Foutrespons: `LLMResponse(success=False, error_message="Connection refused")` als Ollama niet bereikbaar is; `LLMResponse(success=False, error_message="HTTP 404: model not found")` als het model ontbreekt
- Uitzonderingen: Caller-gespecificeerde `format` overschrijft de default niet; `OllamaProvider` is de productie-aanbeveling voor JSON-mode

---

## [BE-SVC-010d] OllamaClient.chat_completion() -- format payload-inclusie

### 1. Type

- Service-methode (utility -- geen HTTP-endpoint)

### 2. Locatie

- Bestandspad: src/core/llm/llm_client.py
- Klasse / functie: `OllamaClient.chat_completion()`

### 3. Gerelateerde flow

- BE-SVC-010-F2 (Ollama JSON-mode completion)

### 4. Doel

- Uitbreiden van `chat_completion()` zodat de `format` kwarg wordt opgenomen in het HTTP-payload naar de Ollama `/api/generate` endpoint. Zonder deze uitbreiding had `complete_json()` wel de kwarg ingesteld, maar werd die nooit naar Ollama doorgestuurd.

### 5. Functionele beschrijving

- Als `format` aanwezig is in kwargs, wordt de waarde opgenomen in het JSON-payload van het HTTP-verzoek aan Ollama. Ollama interpreteert `"format": "json"` als instructie om JSON-gestructureerde output te produceren.

### 6. Technische beschrijving

- Toevoeging in payload-bouwstap: `if kwargs.get("format"): payload["format"] = kwargs["format"]`
- Payload wordt uitgebreid na de basisvelden (`model`, `prompt`, `stream`)
- Geen andere wijzigingen aan de methode-logica

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t.
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: n.v.t.
- Feature flag: n.v.t.

### 8. Request-specificatie

- Methode: n.v.t. -- utility klasse zonder HTTP-endpoints
- Route: n.v.t. -- utility klasse zonder HTTP-endpoints
- Path parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Query parameters: n.v.t. -- utility klasse zonder HTTP-endpoints
- Request body (schema): n.v.t. -- utility klasse zonder HTTP-endpoints
- Verplichte headers: n.v.t. -- utility klasse zonder HTTP-endpoints

### 9. Response-specificatie

- Successtatus: n.v.t. -- utility klasse zonder HTTP-endpoints
- Response schema: `LLMResponse` (zie BE-SVC-010a sectie 9)
- Foutstatussen: n.v.t. -- utility klasse zonder HTTP-endpoints

### 10. Validaties en constraints

- `format` wordt opgenomen als de kwarg een truthy waarde heeft

### 11. Business rules

- Ollama accepteert `"format": "json"` als valide waarde op het `/api/generate` endpoint

### 12. Afhankelijkheden

- `aiohttp` (deferred import)
- Ollama API op `{OLLAMA_BASE_URL}/api/generate`

### 13. Foutafhandeling

- Identiek aan BE-SVC-010c sectie 13; geen aanvullende foutpaden door de uitbreiding

### 14. Transacties en dataIntegriteit

- Geen database-operaties

### 15. Telemetry / logging / tracing

- Identiek aan BE-SVC-010a sectie 15

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- Als `format` aanwezig is in kwargs, bevat het HTTP-payload de sleutel `format` met de opgegeven waarde
- Als `format` niet aanwezig is in kwargs, bevat het HTTP-payload de sleutel `format` niet

### 18. Integratoruitleg

- n.v.t. -- utility klasse zonder HTTP-endpoints; de uitbreiding is transparant voor interne callers

### 19. Trainingssamenvatting

Flow: format wordt opgenomen in het Ollama HTTP-payload

- Actor: `OllamaClient.complete_json()` (interne aanroeper)
- Voorwaarde: `kwargs["format"]` is aanwezig en truthy na `setdefault` in `complete_json()`
- Actie (request): `await self.chat_completion(messages, format="json")`
- Systeemverwerking: payload-bouwstap voegt `"format": "json"` toe; POST naar `{OLLAMA_BASE_URL}/api/generate`
- Succesrespons: Ollama retourneert JSON-gestructureerde content; `LLMResponse(success=True, content=<json>)`
- Foutrespons: Ollama niet bereikbaar of model ontbreekt; `LLMResponse(success=False, error_message=str(e))`
- Uitzonderingen: geen `format` in kwargs -> sleutel wordt niet toegevoegd aan payload

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

n.v.t. -- utility klasse zonder HTTP-endpoints. De `complete_json()` methoden zijn interne service-methoden die door `LLMHandler`, `CopilotService` en `FocusBuilderService` worden aangeroepen als onderdeel van de LLM-failoverchain (ADR-026).

Voor interne callers die een JSON-completion willen aanvragen:

- Gebruik `await client.complete_json(messages, schema=MijnSchema)` -- JSON-mode wordt automatisch ingesteld
- Controleer altijd `response.success` voor het aanroepen van `model_validate_json(response.content)` (CLAUDE.md SP-H03 valkuil)
- `OllamaProvider` verdient de voorkeur boven `OllamaClient` voor productie-JSON-mode (betere message semantics via `/api/chat`)
- De clients zijn stateless; tenant-context bevindt zich uitsluitend in de aanroepende service

---

## Open aannames

- Schema-parameter (`schema: type[Any]`) wordt door de client niet geinspecteerd of gebruikt voor validatie. Aanname: callers doen zelf `model_validate_json()` na ontvangst van de `LLMResponse`. Dit is conform het bestaande patroon in `LLMHandler` (zie SP-H03).
- Ollama `/api/generate` endpoint met `format="json"` produceert valide JSON; dit is afhankelijk van het geinstalleerde Ollama-model en wordt niet gegarandeerd door de client.

## Open vragen

- Moet `schema` ooit worden gebruikt voor client-side response-validatie? Op dit moment niet -- post-MVP evaluatiepunt.
- Moet `OllamaClient` worden gemigreerd naar het `/api/chat` endpoint (zoals `OllamaProvider`)? Buiten scope van B-025; aanbeveling: documenteer als technische schuld.

## Risico's

- `OllamaClient.chat_completion()` gebruikt het `/api/generate` endpoint, dat geen native message-list semantics heeft. JSON-output kan minder betrouwbaar zijn dan via `OllamaProvider` met `/api/chat`. Risico: laag voor MVP; hoog als Ollama de primaire provider wordt.
- DeepSeek API `response_format` wordt ongewijzigd doorgegeven; als een caller een incorrect format meegeeft, retourneert DeepSeek een HTTP 400. De failoverchain vangt dit op.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- 6/6 unit tests PASS
- [x] Alle foutstatus-codes getest -- `success=False` paden getest via mock HTTP-fouten
- [ ] Auth en permissies getest -- n.v.t. (geen HTTP-endpoint); intern gebruik vereist geen auth
- [ ] Tenant-isolatie getest -- n.v.t. (stateless client; tenant-context zit in aanroeper)
- [x] Validaties getest (ongeldige invoer) -- setdefault-gedrag getest; caller-override getest
- [x] Edge cases getest (leeg, null, grenzen) -- `NotImplementedError` afwezigheid getest voor Ollama
- [ ] Dataïntegriteit en transacties getest -- n.v.t. (geen database-operaties)
- [ ] Performance / load getest (indien relevant) -- niet van toepassing voor unit tests; load-test verantwoordelijkheid van de failoverchain
- [ ] Caching getest (indien van toepassing) -- n.v.t. (geen caching)
- [x] Logging en tracing gecontroleerd -- `_update_metrics()` wordt aangeroepen via `chat_completion()`

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
- [x] Review door reviewer-prompt: APPROVED WITH MINOR GAPS
