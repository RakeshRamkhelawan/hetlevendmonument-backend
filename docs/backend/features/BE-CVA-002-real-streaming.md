# Backend Feature Specification

## Metadata

- Feature ID: BE-CVA-002
- Feature naam: CVA Real LLM Streaming
- Status: Gereed
- Auteur: Claude Sonnet 4.6 (via Rakesh)
- Reviewer: Gate 2 code-reviewer + security-reviewer (CHANGES_REQUESTED -> alle HIGH/CRITICAL fixes toegepast)
- Datum: 2026-06-20
- Gerelateerde user story / ticket: CVA Full-Audit Fix Plan Batch F (B1 — nep-streaming vervangen)
- Gerelateerde router / module: `src/core/api/v1/cva/chat_router.py`
- Gerelateerde frontend endpoints: `POST /api/v1/cva/chat/stream`
- Gerelateerde database tabellen: `conversations`, `conversation_messages`
- Versie: 1.0

---

## Doel en scope

### Doel

De `/chat/stream` endpoint simuleerde streaming door de volledige LLM response te wachten en daarna in 30-character brokken te versturen. Dit klokte als streaming maar gaf geen lagency-voordeel. Batch F vervangt dit door echte token-voor-token SSE streaming vanuit de LLM provider.

### In scope

- `DeepSeekProvider.stream()` — OpenAI-compatibel SSE via `httpx.AsyncClient.stream()`
- `GeminiProvider.stream()` — Gemini `streamGenerateContent` SSE endpoint
- `LLMService.stream_generate()` — orchestratielaag: token budget, semantic cache, provider fallback
- `CVAService.chat_stream()` — transactie-veilige streaming: user msg flush voor streaming, assistant commit na
- `chat_router.py` — streaming endpoint herschreven: rate limiting, scope-check, anyio timeout, LLM error handlers
- Security fixes in `generate()` van beide providers:
  - Gemini: API key via `x-goog-api-key` header (niet als URL query param)
  - DeepSeek: `temperature if not None else` patroon (falsy-zero bug gefixed)
  - Gemini: debug log met `%s` stijl + `logger.debug` (niet `logger.info`)

### Out of scope

- Ollama streaming (Ollama's `base.py.stream()` is already implemented — `supports_streaming` op subclass)
- Streaming pariteit voor `confidence`, `suggestions`, `actions` (deze velden komen alleen via `/chat`)
- Token count nauwkeurigheid bij streaming (approximatie: len(chars)//4)

---

## Build summary

- Nieuw gebouwd: `DeepSeekProvider.stream()`, `GeminiProvider.stream()`, `LLMService.stream_generate()`, `CVAService.chat_stream()`
- Gewijzigd: `GeminiProvider.generate()` (API key header + log fixes), `DeepSeekProvider.generate()` (temperature bug), `chat_router.py` streaming endpoint (volledig herschreven)
- Verwijderd: Nep-streaming loop (chunked `generate()` + `for i in range(0, len, 30)`)
- Beinvloede flows: BE-FLW-CVA-002 (streaming chat)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SVC-035 | DeepSeekProvider.stream() | Provider methode | `src/core/services/llm/providers/deepseek.py` | Nieuw | BE-FLW-CVA-002 |
| BE-SVC-036 | GeminiProvider.stream() | Provider methode | `src/core/services/llm/providers/gemini.py` | Nieuw | BE-FLW-CVA-002 |
| BE-SVC-037 | LLMService.stream_generate() | Service methode | `src/core/services/llm/service.py` | Nieuw | BE-FLW-CVA-002 |
| BE-SVC-038 | CVAService.chat_stream() | Service methode | `src/core/services/cva_service.py` | Nieuw | BE-FLW-CVA-002 |
| BE-API-039 | chat_with_cva_streaming() | API endpoint | `src/core/api/v1/cva/chat_router.py` | Wijziging | BE-FLW-CVA-002 |

---

## API-flows

### Flow ID: BE-FLW-CVA-002

- Naam: CVA Streaming Chat
- Trigger: `POST /api/v1/cva/chat/stream`
- Voorwaarden: JWT-token of httpOnly cookie; `tenant_id` uit JWT; rate limit: 10/min per user
- Request-pad: `chat_router.py` -> `CVAService.chat_stream()` -> `LLMService.stream_generate()` -> `DeepSeekProvider.stream()` of `GeminiProvider.stream()`
- Service-stappen:
  1. Scope-check: als `system_prompt` aanwezig, vereist `ADMIN_ALL` (403 anders)
  2. `CVAService.chat_stream()` aangeroepen — geeft `AsyncGenerator[str, None]` terug
  3. Eerst `yield json.dumps({"conversation_id": N})` — vlak na conversation aanmaken/ophalen
  4. User message opgeslagen via `db.flush()` VOOR streaming start
  5. LLM tokens gestreamd via `provider.stream()`, elke chunk `yield json.dumps({"content": chunk})`
  6. Na streaming (of bij client disconnect): assistant message + commit in `try/finally`
  7. Server-side timeout: `anyio.fail_after(120)` rond de generator
- DB-operaties: INSERT conversation_messages (user, flush), INSERT conversation_messages (assistant, commit), UPDATE conversations (title + updated_at)
- Successtatus: `200 OK` met `text/event-stream` body
- Foutpaden: 429 (rate limit), 403 (scope), 503 (LLM timeout/service), 429 (LLM rate limit)
- Eindtoestand: messages persisteren in DB ook bij client disconnect (via finally-block)

---

## Detaildocumentatie per artefact

---

## [BE-SVC-035/036] DeepSeekProvider.stream() + GeminiProvider.stream()

### Technische beschrijving

**DeepSeek (OpenAI-compatible SSE):**
```python
async def stream(self, messages, temperature=None, max_tokens=None) -> AsyncGenerator[str, None]:
    payload = {
        "model": self.config.model,
        "messages": [...],
        "stream": True,
        "temperature": temperature if temperature is not None else self.config.temperature,
        "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
    }
    headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=self.config.timeout) as client:
        async with client.stream("POST", f"{self.config.base_url}/chat/completions",
                                  headers=headers, json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    delta = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                    if delta: yield delta
```

**Gemini (SSE via `streamGenerateContent`):**
- API key via `x-goog-api-key` header (niet als URL param — voorkomt leakage in proxy logs)
- `params={"alt": "sse"}` voor SSE mode
- Payload inline gebouwd (geen `_build_payload()` methode)
- Chunked parsing via `candidates[0]["content"]["parts"][0]["text"]`

**Security correcties in bestaande `generate()`:**
- Gemini: `params={"key": api_key}` vervangen door `headers={"x-goog-api-key": api_key, ...}` 
- Gemini: error body `response.text[:2000]` verwijderd uit logs (PII-risico)
- Gemini: `raise LLMServiceError(f"Gemini API error: {e}")` → `raise LLMServiceError("Gemini API error")` (URL-leakage via exception string)
- Gemini: `logger.info(f"...")` → `logger.debug("...", %s stijl)` (debug log, geen PII)
- DeepSeek: `temperature or self.config.temperature` → `temperature if temperature is not None else self.config.temperature` (falsy-zero bug)

---

## [BE-SVC-037] LLMService.stream_generate()

### Technische beschrijving

```python
async def stream_generate(self, messages, system_prompt=None, temperature=None,
                           max_tokens=None, tenant_id=None) -> AsyncGenerator[str, None]:
    # 1. Zelfde bericht-conversie als generate()
    # 2. System prompt prepend (zelfde volgorde als generate())
    # 3. Cache check — yield cache hit in chunks zonder LLM call
    # 4. Token budget check voor streaming start
    # 5. Stream via provider.stream() of fallback naar generate() + chunking
    # 6. Token budget bijwerken (approximatie: len(chars)//4 voor streaming providers)
    # 7. Cache store na streaming compleet
```

- Fallback: als provider `supports_streaming=False`, volledig genereren + in 30-char chunks yielden
- Token budget approximatie is conservatief (4 chars/token) — echte usage onbekend bij streaming

---

## [BE-SVC-038] CVAService.chat_stream()

### Technische beschrijving

Option B transactie-model (veiligst bij client disconnect):

```
GET/CREATE conversation (flush)
YIELD {"conversation_id": N}
BUILD message history
ADD user_msg + FLUSH
try:
    STREAM LLM tokens → YIELD {"content": chunk}
finally:
    if accumulated content:
        ADD assistant_msg
        conversation.title / updated_at bijwerken
        COMMIT  (of ROLLBACK bij fout)
    else:
        ROLLBACK
```

- User message wordt geflushed VOOR streaming start — survives client disconnect
- Assistant message wordt gecommit in `finally` — ook bij client disconnect wordt partial response opgeslagen
- Episodic memory write is NIET geimplementeerd voor streaming (zou background task vereisen na finally)

---

## [BE-API-039] chat_with_cva_streaming()

### Wijzigingen t.o.v. voor Batch F

| Aspect | Voor | Na |
|--------|------|-----|
| Rate limiting | Geen | `@consent_update_limit` (10/min per user) |
| System prompt guard | Ontbreekt | Gelijke check als `/chat` — 403 als geen ADMIN_ALL |
| Streaming methode | Fake: `chat()` + chunking | Echt: `chat_stream()` + provider.stream() |
| Server-side timeout | Geen | `anyio.fail_after(120)` |
| LLM error handlers | Alleen ValueError + Exception | + LLMTimeoutError, LLMRateLimitError, LLMServiceError |
| DB transaction | Commit alleen na volledige chat() | Flush user msg voor streaming, commit assistant na via finally |

---

## Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT Bearer of httpOnly cookie (`access_token`)
- Vereiste rol/scope: `chat:write` (via `get_current_user`); `ADMIN_ALL` voor system_prompt override
- Tenant-isolatie: `tenant_id` uit JWT; alle DB-writes gebruiken `tenant_id` uit `current_user`
- Rate limit: 10 requests/minuut per user (via `consent_update_limit`)

---

## Acceptatiecriteria

- `/chat/stream` stuurt echte streaming tokens (niet alles tegelijk)
- Eerste SSE event bevat `{"conversation_id": N}`
- Volgende SSE events bevatten `{"content": "<token>"}`
- Laatste SSE event is `[DONE]`
- Bij LLM timeout: SSE error event + `[DONE]` (geen 500, geen hang)
- `pyright` en `ruff` tonen 0 nieuwe errors
- Rate limit: 11e request binnen 1 minuut krijgt 429
- system_prompt zonder ADMIN_ALL scope: 403

---

## Open aannames

- Episodic memory write na streaming wordt in een toekomstige sprint toegevoegd (background task patroon al beschikbaar via `chat()`)
- Token count approximatie (len//4) wordt later vervangen door exacte streaming usage data als providers dat aanbieden
- Ollama streaming: `OllamaProvider` implementeert al `stream()` — werkt automatisch via `stream_generate()`

## Risico's

- Partial response bij client disconnect: gemitigeerd door `try/finally` in `chat_stream()` — user message altijd bewaard, assistant response zo veel als gestreamd
- API key leakage in logs: gemitigeerd door `x-goog-api-key` header (Gemini) en geen exception-interpolatie in error messages

---

## QA-checks

- [x] pyright 0 errors op alle gewijzigde bestanden
- [x] ruff clean
- [ ] E2E streaming test: curl met `--no-buffer`
- [ ] Rate limit test: 11 requests in 1 minuut → 429
- [ ] Client disconnect test: partial response in DB na abort

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Security correcties toegepast (Gate 2 findings)
- [x] pyright + ruff groen
- [ ] Review: APPROVED of APPROVED WITH MINOR GAPS


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: CVA Full-Audit Batch F: DeepSeekProvider.stream() — OpenAI-compat SSE + temperature falsy-zero fix. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt CVA Full-Audit Batch F: DeepSeekProvider.stream() — OpenAI-compat SSE + temperature falsy-zero fix..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
