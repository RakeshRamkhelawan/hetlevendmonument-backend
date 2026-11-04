# BE-SEC-038 -- Copilot WebSocket hardening (PromptGuard + single-execution + rate limit + token + tenant-cleanup)

- Feature ID: BE-SEC-038
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 6 (geconsolideerd 6+7)
- Branch: `iter/ws-hardening`
- Reviewer: code-reviewer (CHANGES_REQUESTED -> minors gefixt) + security-reviewer (APPROVED)
- Datum: 2026-07-10
- ADR: ADR-015 (agent/tool safety + HITL), ADR-027 (Council/turn), ADR-003 (tenant identity)

---

## Doel

Het copilot-WebSocket-pad (`src/core/copilot/api/chat_websocket.py`) even sterk harden als
het reeds gehardende HTTP-pad (`src/core/copilot/api/turn_endpoint.py`). Dag 5 zette de
sidebar op het HTTP-turn-pad; deze dag maakt het WS-pad veilig voor later gebruik. Security-
kritiek omdat de muterende copilot-tools sinds Dag 4 live zijn (create/update/delete taken).

## Scope (5 gaten gedicht)

| ID | Gat | Fix |
| --- | --- | --- |
| SEC-AGT-001 | Geen PromptGuard op WS-input | `_prompt_guard.sanitize(content, tenant_id=...)` voor elke LLM-call; injectie -> error-frame, geen opslag/forward |
| SEC-AGT-002 | Turn draaide 2x | Assistant-reply uit de `done`-chunk i.p.v. tweede `handle_turn`-aanroep; `handle_turn_stream` draait de turn (en actie) exact 1x |
| SEC-AGT-003 | Geen rate limit op WS | `check_copilot_turn_limit(tenant, user) -> bool` (zelfde key/backends als de HTTP-decorator); over de limiet -> error-frame, geen executie |
| SEC-AGT-004 | Token via `?token=` in URL | Query-param verwijderd uit `_extract_token` (OWASP ASVS V7); cookie/subprotocol/Authorization-header blijven. App-breed + FE `FocusModeBuilder` op cookie-auth |
| TI-112/BPA-024 | Tenant-context nooit gecleared | `clear_tenant_context()` in `finally` en op beide early-return foutpaden |

## Gewijzigde bestanden

- `src/core/copilot/api/chat_websocket.py` -- PromptGuard, single-execution, rate-limit-call, tenant-cleanup
- `src/core/auth/websocket_auth.py` -- `?token=` query-param verwijderd uit `_extract_token`
- `src/core/governance/rate_limiter.py` -- nieuwe `check_copilot_turn_limit` (HTTP-decorator ongemoeid)
- `frontend/src/components/workflow/FocusModeBuilder.tsx` -- geen JWT meer in de WS-URL
- `tests/unit/copilot/api/test_ws_hardening.py` (nieuw) + 3 auth-testbestanden bijgewerkt

## Technische beschrijving

- **PromptGuard-pariteit:** dezelfde `PromptGuard()`-instantie-stijl en `sanitize`-aanroep als
  `turn_endpoint.py:61`. De enige door de gebruiker gecontroleerde LLM-invoer is `content`;
  `context["history"]` wordt herbouwd uit eerder gesaneerde, opgeslagen berichten.
- **Single-execution:** `handle_turn_stream` roept intern al `handle_turn` aan en levert de
  volledige response in de `done`-chunk (`{"type":"done","payload": response.model_dump()}`).
  De WS-handler leest `payload["message"]` en persisteert die; de tweede `handle_turn` is weg.
- **Rate limit:** key `copilot_turn:{tenant_id}:{user_id}` (JWT-afgeleid, nooit header), Redis-
  backed met in-memory fallback -- identiek aan de HTTP-decorator. Retourneert `bool` zodat de
  WS-handler een error-frame stuurt i.p.v. een HTTP 429.
- **Token-auth:** OWASP ASVS V7 verbiedt sessie-tokens in URL query strings (lekken in logs,
  history, proxies, Referer). Cookie (canoniek), subprotocol en Authorization-header blijven.
- **Tenant-lifecycle:** `clear_tenant_context()` in het `finally` en op de twee early-return
  foutpaden (db-not-ready, service-build-fail).

## Tests

- `tests/unit/copilot/api/test_ws_hardening.py`: injectie geweigerd (turn start niet), single-
  execution (exact 1 `handle_turn_stream`-call, geen `handle_turn`-re-run), rate limit blokkeert
  voor executie, query-param-token geweigerd, cookie-token geaccepteerd, tenant-context gecleared
  bij disconnect, op de db-not-ready early-return en wanneer de `session_init`-send faalt (de seam
  tussen auth en de receive-loop -- client dropt in dat venster), happy-path stream + cleanup.
- Auth-tests bijgewerkt: token-levering via cookie/subprotocol; query-param wordt geweigerd.

## Acceptatiecriteria

- WS weigert prompt-injectie net als HTTP (geen LLM-call, geen opslag).
- Een enkel WS-`message` voert de turn exact 1x uit.
- WS-chat handhaaft een rate limit; over de limiet geen executie.
- Een token in de URL query string wordt nooit geaccepteerd; cookie/subprotocol/header wel.
- Tenant-context is leeg na afloop/verbreken en op elke early-return.

## Trainingssamenvatting

### Flow 1: Governed copilot-turn over WebSocket

- Actor: ingelogde gebruiker met een geldige sessie (cookie/subprotocol) op de copilot-WS.
- Voorwaarde: WS-verbinding geauthenticeerd; tenant-context gezet uit het JWT.
- Actie: verzendt een `message`-frame met tekst.
- Systeemreactie: PromptGuard saneert de input; rate limit wordt gecheckt; `handle_turn_stream`
  draait de Council-turn exact 1x en streamt `chunk`- + `done`-frames; de assistant-reply uit de
  `done`-chunk wordt in het conversatiegeheugen opgeslagen.
- Succesrespons: gestreamd antwoord; muterende actie exact 1x uitgevoerd.
- Foutrespons: injectie -> `{"type":"error","message":"Input rejected"}`; over de limiet ->
  `{"type":"error","message":"Rate limit exceeded"}`; geen executie in beide gevallen.
- Uitzonderingen: token alleen via cookie/subprotocol/header (nooit URL); tenant-context wordt
  altijd gecleared bij afloop, verbreken of early-return.

## Definition of Done

- [x] Alle 5 gaten gedicht; rode tests waren ROOD voor de fix, nu GROEN
- [x] Gate 2: code-reviewer (na minors) + security-reviewer APPROVED
- [x] Gate 3: ruff 0, pyright 0 (expliciet op de gewijzigde bestanden), gerichte tests groen
- [x] Feature-spec + review APPROVED, ID-REGISTRY bijgewerkt
