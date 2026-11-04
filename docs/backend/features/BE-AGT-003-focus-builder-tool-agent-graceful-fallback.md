# BE-AGT-003 -- FocusBuilderToolAgent _dispatch_tools Graceful Fallback

**Sprint:** SP-WE-22
**Bron:** NEW-WIRE-006
**ADR:** ADR-023
**Datum:** 2026-06-01
**Status:** APPROVED

## Samenvatting

`_dispatch_tools()` in `FocusBuilderToolAgent` gooide een `NotImplementedError` die alleen
impliciet werd gevangen door de `try/except Exception` in `handle_message()`. De fix maakt
de fallback-delegatie expliciet, vervangt de exception door een gestructureerde
`logger.warning` met `tenant_id`, en roept `self._fallback.handle_message(content)` direct
aan.

## Gewijzigde bestanden

- `src/core/agents/focus_builder_tool_agent.py` (regel 134-138 -> 134-146)
- `tests/unit/test_sp_we_22_focus_builder_not_implemented.py` (nieuw, 5 tests)

## Gedragswijziging

- **Voor fix:** `_dispatch_tools()` gooide `NotImplementedError`; `handle_message()` ving dit
  op via `except Exception` en logde een generieke `tool_agent_fallback` warning met
  exception-stringification. Bij directe aanroep van `_dispatch_tools()` (buiten
  `handle_message()`) crashte de stack volledig.
- **Na fix:** `_dispatch_tools()` logt een gestructureerde WARNING met `tenant_id` en
  `tool_count`, en delegeert expliciet naar `self._fallback.handle_message(content)`.
  Geen exception meer; `handle_message()`'s `try/except` blijft als veiligheidsnet.

## Trainingssamenvatting

### Flow: Gebruiker stuurt bericht via FocusBuilderToolAgent

- **Actor:** Eindgebruiker via Focus Builder UI (`FOCUS_BUILDER_TOOL_AGENT=true`)
- **Voorwaarde:** `FocusBuilderToolAgent` is actief; tool-calling LLM loop is nog niet
  geimplementeerd (scaffold)
- **Actie:** Gebruiker stuurt een chatbericht
- **Systeemverwerking:**
  1. `handle_message(content)` wordt aangeroepen
  2. `_dispatch_tools(content)` wordt aangeroepen
  3. `logger.warning()` wordt geroepen met `extra={"tenant_id": ..., "tool_count": ...}`
  4. `self._fallback.handle_message(content)` wordt aangeroepen
  5. `FocusBuilderChatAgent` verwerkt het bericht
- **Succesrespons:** Gebruiker krijgt antwoord via `FocusBuilderChatAgent`; geen zichtbaar
  verschil ten opzichte van de bestaande fallback-flow
- **Foutrespons:** Als `_fallback.handle_message()` zelf een exception gooit, bubbelt deze
  naar `handle_message()`, die hem opvangt via de bestaande `except Exception` en opnieuw
  via de fallback probeert te delegeren (bestaand veiligheidsnet).
- **Uitzonderingen:** `FOCUS_BUILDER_TOOL_AGENT=false` -> `FocusBuilderToolAgent` wordt niet
  gebruikt; dit codepad is dan niet bereikbaar.

## Test verificatie

- `tests/unit/test_sp_we_22_focus_builder_not_implemented.py` (5 tests, alle PASS)
  - `test_dispatch_tools_does_not_raise`
  - `test_dispatch_tools_logs_warning_not_implemented`
  - `test_dispatch_tools_delegates_to_fallback`
  - `test_handle_message_does_not_raise_when_dispatch_unimplemented`
  - `test_dispatch_tools_no_not_implemented_error_raised`

## Compliance

- ASCII-only in code en log-strings (em-dash uit oude exception verwijderd)
- `tenant_id` uit `self.tenant_id` (JWT-derived), niet uit request body
- Geen PII gelogd (content van de gebruiker NIET in log)
- Geen hardcoded URLs of secrets
