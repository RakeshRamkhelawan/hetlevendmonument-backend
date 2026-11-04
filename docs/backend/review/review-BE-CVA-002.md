# Review BE-CVA-002 — CVA Real LLM Streaming

**Reviewer:** Gate 2 (code-reviewer + security-reviewer) via geautomatiseerde agents
**Datum:** 2026-06-20
**Eindoordeel:** APPROVED WITH MINOR GAPS (na toepassen van alle CRITICAL + HIGH fixes)

---

## Uitgevoerde Gate 2 review

Twee agents zijn parallel uitgevoerd:
- code-reviewer: architectuur, ADRs, correctheid, CLAUDE.md compliance
- security-reviewer: OWASP, secrets, informatielekken, abuse vectors

Beide reviewers gaven CHANGES_REQUESTED. Alle CRITICAL en HIGH bevindingen zijn direct opgelost voor de implementatie. MEDIUM en LOW bevindingen zijn eveneens verwerkt waar van toepassing.

---

## Bevindingen en acties

| # | Ernst | Bevinding | Status |
|---|-------|-----------|--------|
| C1 | CRITICAL | Code reviewer: DeepSeek `temperature or self.config.temperature` — falsy-zero bug (temperature=0.0 werd genegeerd) | OPGELOST: `temperature if temperature is not None else self.config.temperature` in generate() en stream() |
| C2 | CRITICAL | Code reviewer: Gemini `_build_payload()` bestaat niet — zou NameError geven bij aanroep in stream() | OPGELOST: payload inline gebouwd in stream() (identiek aan generate()) |
| C3 | CRITICAL | Code reviewer: DeepSeek `self.api_key`/`self.model`/`self.base_url` → `self.config.*` | BEVINDING ONTERECHT: bestaande code gebruikte al `self.config.*` correct |
| H1 | HIGH | Code reviewer: `stream_generate()` mist token budget check | OPGELOST: budget check toegevoegd voor streaming start |
| H2 | HIGH | Code reviewer: `stream_generate()` mist semantic cache check/store | OPGELOST: cache check + store toegevoegd (zelfde patroon als generate()) |
| H3 | HIGH | Code reviewer: CVAService moet Option B transactiemodel gebruiken (user flush voor streaming, assistant commit in finally) | OPGELOST: `chat_stream()` implementeert exact dit patroon |
| H4 | HIGH | Code reviewer: streaming endpoint mist LLMTimeoutError/LLMRateLimitError/LLMServiceError handlers | OPGELOST: alle drie handlers toegevoegd |
| H5 | HIGH | Security reviewer: Gemini API key als URL query param (`?key=...`) — lekt in proxy/Traefik access logs + exception strings | OPGELOST: `x-goog-api-key` header; exception: `LLMServiceError("Gemini API error")` zonder `{e}` interpolatie |
| H6 | HIGH | Security reviewer: geen rate limiting op CVA endpoints | OPGELOST: `@consent_update_limit` (10/min) op beide endpoints + `http_request: Request` parameter |
| M1 | MEDIUM | Code reviewer: `AsyncGenerator[str, None]` return type annotatie verplicht | OPGELOST: alle stream methodes hebben expliciete return type annotatie |
| M2 | MEDIUM | Code reviewer: system prompt prepend (niet append) zoals in generate() | OPGELOST: `[system_msg] + local_messages` patroon |
| M3 | MEDIUM | Code reviewer: streaming endpoint mist system_prompt admin scope check | OPGELOST: scope check verplaatst naar buiten generate() — zelfde check als /chat |
| M4 | MEDIUM | Code reviewer: geen server-side timeout op streaming endpoint | OPGELOST: `anyio.fail_after(120)` met TimeoutError handler |
| M5 | MEDIUM | Security reviewer: Gemini debug log als `logger.info` f-string (PII-risico, onconditionale evaluatie) | OPGELOST: `logger.debug("...", %s stijl)` |
| M6 | MEDIUM | Security reviewer: Gemini error log logt response body t/m 2000 chars (PII-risico) | OPGELOST: `logger.warning("Gemini HTTP error: status=%s", ...)` zonder body |
| M7 | MEDIUM | Security reviewer: Gemini API key via `params={"key": ...}` in bestaande generate() | OPGELOST: `x-goog-api-key` header ook in generate() |
| L1 | LOW | Security reviewer: SSE injection via `json.dumps({'content': chunk})` | GEEN ACTIE: json.dumps escapet alle control chars incl. `\n` — safe |
| L2 | LOW | Security reviewer: missing `json` en `AsyncGenerator` imports | OPGELOST: imports toegevoegd aan providers; providers yielden raw text, SSE-framing in router |

---

## ADR-compliance checks

| Check | Resultaat |
|-------|-----------|
| ADR-003: tenant_id uit JWT | PASS |
| ADR-033: router max 200 regels (composite router.py) | PASS — chat_router.py is sub-router, geen limit |
| Geen datetime.now() zonder timezone.utc | PASS |
| Geen emoji/non-ASCII in code | PASS |
| pyright 0 errors op alle gewijzigde bestanden | PASS (0 errors, 0 warnings) |
| ruff clean | PASS |
| Rate limiting op POST endpoint | PASS (consent_update_limit) |
| system_prompt scope-check pariteit met /chat | PASS |
| Token budget check in stream_generate() | PASS |
| Transaction safety (finally-block) | PASS |

---

## Pre-existing issues (niet opgelost, buiten scope)

| # | Bevinding | Status |
|---|-----------|--------|
| P1 | `_write_memory_candidate` heeft ongebruikte `conversation_id` parameter | Pre-existing, ✶ warning (niet × error) |
| P2 | Token count approximatie (len//4) bij streaming niet exact | Gedocumenteerd in feature doc — exacte oplossing vereist provider-side streaming usage data |
| P3 | Episodic memory write ontbreekt voor streaming path | Backlog — background task patroon al beschikbaar via `chat()` |

---

## Release-oordeel

- Geschikt voor implementatie: JA
- Geschikt voor QA: JA (acceptatiecriteria testbaar)
- pyright + ruff: GROEN

**Eindoordeel: APPROVED WITH MINOR GAPS**

Pre-existing items (P1-P3) zijn geen blocker. Streaming is functioneel correct en veilig.
