# Backend Feature Specification

## Metadata

- Feature ID: BE-CVA-001
- Feature naam: CVA ChatResponse Schema Uitbreiding + CVAAction Model
- Status: Gereed
- Auteur: Claude Sonnet 4.6 (via Rakesh)
- Reviewer: Gate 2 code-reviewer + security-reviewer (APPROVED_WITH_MINOR_ISSUES / CHANGES_REQUESTED -> fixes toegepast)
- Datum: 2026-06-20
- Gerelateerde user story / ticket: CVA Full-Audit Fix Plan Batch D
- Gerelateerde router / module: `src/core/api/v1/cva/chat_router.py`
- Gerelateerde frontend endpoints: `POST /api/v1/cva/chat`
- Gerelateerde database tabellen: `conversations`, `conversation_messages`
- Versie: 1.0

---

## Doel en scope

### Doel

De `ChatResponse` terugsturen door het `/api/v1/cva/chat` endpoint had slechts 3 velden
(`response`, `conversation_id`, `metadata`). De frontend `CVAResponseRenderer` verwachtte
echter 7 velden voor confidence badge, provider badge, suggesties en acties — die kwamen
allemaal als `undefined` binnen. Dit koppelt de schema-definitie aan de frontend-renderer
zodat alle UI-elementen activeren.

### In scope

- Nieuw Pydantic model `CVAAction` met route-validator (open navigation prevention)
- `ChatResponse` uitgebreid met `confidence`, `suggestions`, `actions`, `llm_provider_used`
- `CVAService.chat()` vult de nieuwe velden; return type verbreed naar `dict[str, Any]`
- Stale `# type: ignore` verwijderd uit `chat_router.py`
- Provider-allowlist `_PROVIDER_DISPLAY` beschermt tegen informatielekken

### Out of scope

- `confidence` echte berekening (placeholder `None` — vereist LLM token logprobs)
- Streaming endpoint pariteit (nieuwe velden niet gestreamed — gedocumenteerd als asymmetrie)
- `_get_message_history` tenant_id filter (pre-existing; apart architecture test backlog item)

---

## Build summary

- Nieuw gebouwd: `CVAAction` model in `cva_schemas.py`; `_PROVIDER_DISPLAY` allowlist in `cva_service.py`
- Gewijzigd: `ChatResponse` (+4 velden), `CVAService.chat()` return dict (+4 keys, return type), `chat_router.py` (stale ignore verwijderd)
- Verwijderd: `# type: ignore[arg-type]  # pyright: ignore[reportArgumentType]` op `chat_router.py:121`
- Beinvloede bestaande flows: BE-FLW-CVA-001 (non-streaming chat); streaming endpoint ongewijzigd

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SCH-029 | CVAAction | Pydantic schema | `src/core/schemas/cva_schemas.py` | Nieuw | BE-FLW-CVA-001 |
| BE-SCH-029 | ChatResponse uitbreiding | Pydantic schema | `src/core/schemas/cva_schemas.py` | Wijziging | BE-FLW-CVA-001 |
| BE-SVC-034 | CVAService.chat() return uitbreiding | Service-functie | `src/core/services/cva_service.py` | Wijziging | BE-FLW-CVA-001 |

---

## API-flows

### Flow ID: BE-FLW-CVA-001

- Naam: CVA Non-Streaming Chat
- Trigger: `POST /api/v1/cva/chat`
- Voorwaarden: JWT-token of httpOnly cookie vereist; `tenant_id` uit JWT claim
- Request-pad: `chat_router.py` -> `CVAService.chat()` -> LLMService -> DB
- Service-stappen:
  1. Haal of maak `Conversation` aan (flush, geen commit)
  2. Bouw message history op via `_get_message_history`
  3. Genereer LLM response via `effective_llm.generate()`
  4. Sla user + assistant message op (`db.add` x2)
  5. Update `conversation.title` indien eerste bericht
  6. `await db.commit()` + `await db.refresh(conversation)`
  7. Schrijf episodic memory candidate (fire-and-forget task)
  8. Retourneer extended dict -> `ChatResponse(**result)`
- DB-operaties: INSERT conversation_messages x2, UPDATE conversations (title + updated_at), COMMIT
- Successtatus: `200 OK` + `ChatResponse` JSON
- Foutpaden: ValueError -> 404, LLMTimeoutError -> 503, Exception -> 500
- Eindtoestand: messages persisteren in DB; conversation bijgewerkt

---

## Detaildocumentatie per artefact

---

## [BE-SCH-029] CVAAction + ChatResponse

### 1. Type

- Pydantic BaseModel (request/response schema)

### 2. Locatie

- Bestandspad: `src/core/schemas/cva_schemas.py`
- Klasse: `CVAAction`, `ChatResponse`

### 3. Gerelateerde flow

- BE-FLW-CVA-001

### 4. Doel

`CVAAction` definieert de gesloten discriminated union van acties die de backend aan de
frontend kan aanreiken. `ChatResponse` biedt alle velden die `CVAResponseRenderer` nodig
heeft om confidence badge, provider badge, suggesties en acties te tonen.

### 5. Functionele beschrijving

- `CVAAction.type` is beperkt tot `"navigate_to"`, `"navigate_to_vibe"`, `"suggestion"`
- `CVAAction.route` wordt server-side gevalideerd: moet starten met `/` (geen externe URL)
- `ChatResponse.confidence` is `null` totdat echte LLM-scoring beschikbaar is; renderer toont badge alleen als waarde niet-null
- `ChatResponse.llm_provider_used` toont welke provider de request afhandelde (gemini / deepseek / ollama); `null` voor onbekende of test-providers (via `_PROVIDER_DISPLAY` allowlist)
- `ChatResponse.suggestions` is altijd een lege lijst in MVP; veld is aanwezig voor forward compatibility
- `ChatResponse.actions` is altijd een lege lijst in MVP; veld is aanwezig voor forward compatibility

### 6. Technische beschrijving

**CVAAction:**
```python
class CVAAction(BaseModel):
    type: Literal["navigate_to", "navigate_to_vibe", "suggestion"]
    label: str | None = None
    route: str | None = None
    workflow_data: dict[str, Any] | None = None

    @field_validator("route")
    @classmethod
    def validate_route(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("/"):
            raise ValueError("route must be a relative path starting with '/'")
        return v
```

**ChatResponse nieuw velden:**
```python
confidence: float | None = Field(default=None, ge=0.0, le=1.0)
suggestions: list[str] = Field(default_factory=list)
actions: list[CVAAction] = Field(default_factory=list)
llm_provider_used: str | None = Field(default=None)
```

**_PROVIDER_DISPLAY allowlist in cva_service.py:**
```python
_PROVIDER_DISPLAY: dict[str, str] = {
    "gemini": "gemini",
    "deepseek": "deepseek",
    "ollama": "ollama",
}
```
Providers buiten de allowlist (bijv. "mock") retourneren `None` — informatielek voorkomen.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT Bearer of httpOnly cookie (`access_token`)
- Vereiste rol / scope: `chat:write` (via `get_current_user`)
- Tenant-isolatie: `tenant_id` uit JWT; alle DB-writes gebruiken `tenant_id` uit `current_user`
- Feature flag: geen

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/cva/chat`
- Request body: `ChatRequest` (message, conversation_id?, system_prompt?, mode?, model?)
- Verplichte headers: `Authorization: Bearer <token>` OF `Cookie: access_token=<token>`

### 9. Response-specificatie

- Successtatus: 200 OK
- Response schema: `ChatResponse`
  ```json
  {
    "response": "string",
    "conversation_id": 123,
    "metadata": {"tokens_used": 45, "model": "...", "timestamp": "..."},
    "confidence": null,
    "suggestions": [],
    "actions": [],
    "llm_provider_used": "gemini"
  }
  ```
- Foutstatussen: 401, 403, 404 (conversation niet gevonden), 422, 503 (LLM timeout/unavailable), 500

### 10. Validaties en constraints

- `CVAAction.route`: als aanwezig, moet starten met `/`
- `ChatResponse.confidence`: ge=0.0, le=1.0 (Pydantic constraint)
- Alle nieuwe velden hebben defaults — geen breaking change voor bestaande consumers

### 11. Business rules

- `llm_provider_used` wordt bepaald door `effective_llm` (kan afwijken van geconfigureerde LLM als `model` override meegegeven)
- `confidence=None` betekent expliciet "niet berekend" — frontend toont geen badge
- `actions` die `type="navigate_to_vibe"` bevatten, moeten ook `workflow_data` bevatten (niet afgedwongen door schema, maar contract met frontend)

### 12. Afhankelijkheden

- `LLMService.provider.provider_name` property (base.py:178)
- `_PROVIDER_DISPLAY` module-level constant
- Frontend: `CVAResponseRenderer.tsx`, `CVAMessage` TypeScript type

### 13. Foutafhandeling

- 400: n.v.t. (request errors worden door `ChatRequest` validator opgevangen -> 422)
- 401: ontbrekende token -> `get_current_user` gooit HTTPException
- 403: verkeerde tenant of scope -> HTTPException
- 404: `ValueError` in service -> `handle_cva_value_error` -> 404
- 422: Pydantic validatie `CVAAction.route` niet-relatief pad
- 503: LLMTimeoutError -> HTTPException 503

### 14. Transacties en dataintegiteit

- Geen transactie-wijzigingen t.o.v. voor Batch D
- Nieuw: return dict uitgebreid na `await db.commit()` — geen impact op transactie-integriteit

### 15. Telemetry / logging / tracing

- Bestaande Prometheus metric `cva_chat_duration_seconds` ongewijzigd
- `llm_provider_used` in response — intern al gelogd via `logger.info("... provider=...")` in LLMService

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- POST `/api/v1/cva/chat` retourneert een JSON met `confidence`, `suggestions`, `actions`, `llm_provider_used` velden
- `llm_provider_used` is `"gemini"`, `"deepseek"`, `"ollama"` of `null` — nooit een interne klassenaam
- `actions` item met `route` die niet start met `/` gooit 422
- `confidence` is `null` (niet 0.85)
- `CVAResponseRenderer` toont geen confidence badge wanneer `confidence === null`
- `pyright` en `ruff` tonen 0 nieuwe errors

### 18. Integratoruitleg

- Alle vier nieuwe velden hebben defaults — bestaande API-clients breken niet
- `confidence: null` betekent "nog niet beschikbaar" — toon geen voortgangspercentage aan eindgebruikers
- `llm_provider_used` is informatief; gebruik het niet als routing-logica
- `actions` is in MVP altijd leeg; veld is aanwezig voor toekomstige CVA-navigatie-integratie

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: geldig JWT of cookie; optioneel bestaande conversation_id
- Actie (request): POST /api/v1/cva/chat met message
- Systeemverwerking: LLM genereert antwoord; messages worden persisteerden; return dict bevat nu ook metadata-velden voor frontend renderer
- Succesrespons: 200 OK met `ChatResponse` incl. confidence=null, suggestions=[], actions=[], llm_provider_used=provider|null
- Foutrespons: 401/403 auth, 404 conversation niet gevonden, 503 LLM timeout
- Uitzonderingen: model override -> effective_llm verschilt van geconfigureerde LLM; mock-provider geeft `llm_provider_used=null`

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Voeg niets toe aan je huidige requests — alle nieuwe velden zijn optioneel in de response
- Lees `confidence` als `null` -> toon geen betrouwbaarheidsscore aan eindgebruikers
- Gebruik `llm_provider_used` uitsluitend voor informatieve weergave (bijv. "Powered by Gemini")
- `actions` is beschikbaar voor toekomstige CVA-navigatie; verwerk het als lege lijst tot nader order

---

## Open aannames

- `confidence` wordt in een toekomstige sprint gevuld via token logprobs of een aparte calibration call
- `actions` worden gevuld zodra de LLM structured output voor CVA-navigatie wordt geactiveerd
- Streaming endpoint asymmetrie (nieuwe velden niet gestreamed) is gedocumenteerd en acceptabel voor MVP

## Open vragen

- Wanneer gaat `confidence` echte waarden krijgen? (afhankelijk van LLM provider logprobs support)

## Risico's

- `actions[].route` open navigation: gemitigeerd door `@field_validator` die niet-relatieve paden afwijst
- `llm_provider_used` informatielek: gemitigeerd door `_PROVIDER_DISPLAY` allowlist (mock -> null)

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle nieuwe velden aanwezig in response
- [x] `pyright` 0 errors (CVA files: 0 errors, 0 warnings)
- [x] `ruff` clean op CVA files
- [ ] `confidence=null` getest via geautomatiseerde test
- [ ] `actions` route-validator 422 getest
- [ ] Tenant-isolatie ongewijzigd (pre-existing tests)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
- [x] pyright + ruff groen
- [ ] Review: APPROVED of APPROVED WITH MINOR GAPS
