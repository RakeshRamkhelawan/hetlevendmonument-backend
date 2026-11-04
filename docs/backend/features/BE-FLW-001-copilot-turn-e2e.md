# BE-FLW-001 — CVA copilot/turn End-to-End Flow

**ID:** BE-FLW-001
**Sprint:** SP-G02
**Datum:** 2026-05-29
**Eigenaar:** Rakesh Ramkhelawan
**Status:** APPROVED

---

## Doel

Verifieer en documenteer de volledige POST /api/v1/copilot/turn pipeline na de SP-D01
LLM-fixes. De test suite bewijst dat de CVA-keten (tenant-injectie -> rate-limit ->
authenticatie -> LLMHandler.complete_json() -> AgentCouncil.deliberate() -> respons)
correct werkt.

---

## Scope

| Component | Bestandspad |
|-----------|-------------|
| Turn endpoint | `src/core/copilot/api/turn_endpoint.py` |
| CopilotService | `src/core/copilot/service.py` |
| LLMHandler | `src/core/copilot/llm_handler.py` |
| Schemas | `src/core/copilot/schemas.py` |
| Rate limiter | `src/core/governance/rate_limiter.py` |
| Feature flag | `src/core/config/feature_flags.py` |
| Tenant context | `src/core/middleware/tenant_context.py` |
| Test suite | `tests/unit/test_sp_g02_cva_e2e.py` |

---

## Architectuurbeslissingen

- `require_tenant_id()` roept de ContextVar direct aan (niet via FastAPI Depends).
  De HTTP middleware moet `set_tenant_id()` aanroepen VOOR `call_next` zodat de
  copilot_turn_limit key_func de waarde ziet tijdens route-dispatch.
- `complete_json()` is verplicht voor alle LLM-aanroepen die JSON-output produceren
  (ADR-027 paragraaf 9). `LLMHandler.get_action()` roept dit aan via
  `self._provider.complete_json(messages=..., schema=CopilotAction)`.
- `_rate_limiter` is een module-level singleton in `rate_limiter.py`. Tests moeten
  `_rate_limiter._requests.clear()` aanroepen in `setup_method` om gedeelde staat
  te voorkomen.
- `check_copilot_rollout()` retourneert een `Depends(...)` object — de rollout-check
  is feitelijk een no-op. Override is toch verplicht in tests om CI-omgevingen met
  `COPILOT_COUNCIL_V1_ROLLOUT_PCT=0` niet te laten falen.
- `CopilotTurnResponse` gebruikt `decision_id: str` en `council_summary: dict[str, int]`
  (geen UUID, geen str voor council_summary).

---

## API Contract

### Request

```
POST /api/v1/copilot/turn
Authorization: Bearer <jwt>

{
  "message": "...",        // required, min_length=1, max_length=2000
  "context": {},           // optional
  "stream": false,         // optional, default false
  "language": "nl"         // optional, Literal["nl", "en"], default "nl"
}
```

Verboden velden: `tenant_id` — extra="forbid" gooit 422 als het aanwezig is.

### Response (niet-streaming)

```json
{
  "decision_id": "uuid-string",
  "verdict": "approved|modified|hitl_required|deferred|blocked",
  "message": "...",
  "action": "tool_name|null",
  "action_params": {},
  "confidence": 0.92,
  "council_summary": {},
  "hitl_request_id": "uuid-string|null",
  "explanation_url": "url|null"
}
```

### Response (streaming, stream=true)

```
Content-Type: text/event-stream

data: {"type": "delta", "content": "..."}
data: {"type": "done"}
data: [DONE]
```

---

## Trainingssamenvatting

### Flow 1: Goedgekeurd verzoek (Happy Path)

| Stap | Detail |
|------|--------|
| **Actor** | Ingelogde gebruiker (tenant 1, user 42) |
| **Voorwaarde** | Geldige JWT, rate-limit niet bereikt, COPILOT_COUNCIL_V1_ROLLOUT_PCT >= 100 |
| **Actie** | POST /api/v1/copilot/turn met `{"message": "Help me automate a task."}` |
| **Systeemverwerking** | Middleware zet tenant_id in ContextVar -> copilot_turn_limit controleert bucket -> get_current_user valideert JWT -> require_tenant_id() leest ContextVar -> CopilotService.handle_turn() -> LLMHandler.get_action() (complete_json) -> AgentCouncil.deliberate() -> _execute_decision() |
| **Succesrespons** | HTTP 200, `{"verdict": "approved", "decision_id": "...", "confidence": 0.92, ...}` |
| **Foutrespons** | HTTP 500 bij interne fout, `{"detail": "Internal error"}` |
| **Uitzonderingen** | stream=true: HTTP 200 met Content-Type: text/event-stream; taal invalide: 422 |

### Flow 2: Geblokkeerd door Council

| Stap | Detail |
|------|--------|
| **Actor** | Ingelogde gebruiker |
| **Voorwaarde** | Council-officer keurt actie af |
| **Actie** | POST /api/v1/copilot/turn met gevaarlijk verzoek |
| **Systeemverwerking** | Zelfde als Flow 1 t/m AgentCouncil.deliberate() -> verdict=blocked |
| **Succesrespons** | HTTP 200 (niet 4xx), `{"verdict": "blocked", "message": "..."}` |
| **Foutrespons** | n.v.t. — blocked is geen fout, maar een geldig verdict |
| **Uitzonderingen** | hitl_required: inclusief `hitl_request_id`; deferred: async verwerking |

### Flow 3: Authenticatiefout

| Stap | Detail |
|------|--------|
| **Actor** | Niet-geauthenticeerde client |
| **Voorwaarde** | Ontbrekende of ongeldige JWT |
| **Actie** | POST /api/v1/copilot/turn zonder Authorization header |
| **Systeemverwerking** | get_current_user dependency raise HTTPException(401) VOOR service.handle_turn() |
| **Succesrespons** | n.v.t. |
| **Foutrespons** | HTTP 401, service wordt NIET aangeroepen (bewezen via `assert_not_awaited()`) |
| **Uitzonderingen** | n.v.t. |

### Flow 4: Invoervalidatie

| Stap | Detail |
|------|--------|
| **Actor** | Client met ongeldig verzoek |
| **Voorwaarde** | Lege message, ontbrekend veld, overschreden max_length, ongeldige taal, of tenant_id in body |
| **Actie** | POST /api/v1/copilot/turn met ongeldig body |
| **Systeemverwerking** | Pydantic CopilotTurnRequest.model_validate() gooit ValidationError |
| **Succesrespons** | n.v.t. |
| **Foutrespons** | HTTP 422 met Pydantic foutdetails |
| **Uitzonderingen** | tenant_id in body: 422 via extra="forbid" — geen tenant-spoofing mogelijk |

---

## Testdekking

| Test | Scenario | Verwacht |
|------|----------|----------|
| test_approved_turn_returns_200_with_response_fields | Happy path | 200 + alle velden |
| test_complete_json_is_used_not_raw_llm_text | LLM pipeline | handle_turn aangeroepen |
| test_handle_turn_receives_correct_tenant_and_user | Tenant isolatie | tenant_id=1, user_id=42 |
| test_blocked_verdict_returns_200_with_blocked_verdict | Council block | 200 verdict=blocked |
| test_hitl_required_verdict_includes_hitl_request_id | HITL path | hitl_request_id aanwezig |
| test_tenant_id_not_accepted_in_request_body | Tenant spoofing | 422 |
| test_handle_turn_tenant_id_matches_middleware_not_body | Tenant bron | middleware-waarde |
| test_unauthenticated_request_returns_401_and_service_not_called | Auth | 401 + niet aangeroepen |
| test_empty_message_returns_422 | Validatie | 422 |
| test_missing_message_returns_422 | Validatie | 422 |
| test_message_exceeding_max_length_returns_422 | Validatie | 422 |
| test_english_language_parameter_accepted | Taal | 200 |
| test_invalid_language_returns_422 | Taal | 422 |
| test_streaming_request_returns_event_stream | Streaming | 200 + text/event-stream |

**Totaal: 14 tests — alle groen (SP-G02, 2026-05-29)**
