# Review: BE-SEC-042 — geen token in de query string op websocket-paden

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-SEC-042-websocket-no-query-token.md` |
| Reviewer | Fresh-eyes zelfreview (subagents niet toegestaan in deze sessie; expliciet gemeld aan Rakesh) |
| Datum | 2026-07-31 |
| Uitkomst | **APPROVED** |

---

## Controle tegen de code (geen aannames)

| Claim in spec | Verificatie | Oordeel |
| --- | --- | --- |
| 6 plekken accepteerden een query-token | AST-scan, rood voor de fix met precies die 6 regels; groen na de fix | Correct, empirisch |
| Handmatig grep-werk vond er 3 | Mijn eigen eerdere melding aan Rakesh noemde 3 plekken; de scan vond `websocket/router.py` (2x) en de dode swarm-parameter extra | Correct -- gemeld als correctie |
| Er stond een test die het onveilige gedrag vastlegde | `test_ws_auth_query_param_backward_compat` asserteerde `result_user.email == user_email` bij een token in de query | Correct |
| swarm-parameter was ongebruikt | `swarm_stream_secure` gebruikte `token` nergens; auth liep via `auth.authenticate(websocket)` | Correct -- verwijdering is gedragsneutraal |
| `websocket/router.py` gebruikte het token wel | Beide endpoints gaven `token=` door aan `connection_manager.connect(..., require_auth=True)`; zonder token sluit die met policy violation | Correct -- daar was ombouw nodig, geen verwijdering |
| Frontend gebruikt al cookies | Bron gelezen: `useWebSocket.ts:76`, `useFocusBuilderWS.ts:284` (alleen `conversation_id`), `useFlowStatusWebSocket.ts::buildWebSocketUrl` (geen token) | Correct |
| HTTP-pad heeft geen query-token | `get_token_from_request` leest header + cookie + HTTPBearer-credentials; geen `query_params` | Correct -- restrisico vervalt daarmee |
| DSM fan-out-budget | Met de import in `core_api`: 801 > 800 (test faalde). Na verplaatsing naar de manager: architecture-suite 396 passed | Correct, empirisch |

## Bevindingen

Geen CRITICAL. Geen HIGH.

MEDIUM (opgelost tijdens de review-ronde):
- R1 -- Eerste implementatie zette een `_ws_token`-helper in
  `src/core/api/v1/websocket/router.py`. Dat voegde een architectuurrand `core_api -> auth`
  toe en bracht het DSM fan-out-budget van `core_api` op 801 tegen een plafond van 800
  (`test_dsm_grade_a_plus.py::test_fan_out_budget[core_api-800]`). Opgelost door de
  extractie te verplaatsen naar `websocket/manager.py::connect()`, dat de auth-rand al
  heeft -- functioneel identiek, architectonisch beter (de manager is de enige die het
  token nodig heeft).

MINOR (opgelost):
- R2 -- 5 pre-existing failures in `tests/core/api/v1/focus_builder/test_ws_chat.py`:
  de handler werd geimporteerd uit de ADR-033-composite `router.py`, die hem nooit heeft
  geexporteerd (`ImportError`). Onopgemerkt omdat `tests/core/` buiten zowel
  `pytest tests/unit/` als `pytest tests/integration/` valt. Import gecorrigeerd naar
  `ws_chat_router`, patch-targets meegetrokken, test gebruikt nu de cookie.
- R3 -- Emoji in een `print()` in `tests/integration/test_copilot_websocket.py`
  verwijderd (NOOIT-lijst: geen non-ASCII in code).
- R4 -- Verouderde docstring in `get_current_user` ("Triple-Lock auth
  (header/cookie/query)") gecorrigeerd; er is geen query-pad. Zonder correctie is dat een
  uitnodiging om er later wel een te bouwen.

## Kwaliteitspoorten

- ruff: clean op alle gewijzigde bestanden.
- pyright: 0 errors. NB: de IDE meldde tijdens het werk kort 2 errors op
  `dependencies.py:184/199`; dat bleek verschoven diagnostiek na een
  docstring-wijziging -- de `# type: ignore[assignment]`-comments stonden nog correct op
  hun eigen regels (187/202). Geverifieerd met een echte `python -m pyright`-run, niet op
  de IDE-melding vertrouwd.
- ASCII: geen non-ASCII in code of tests (1 emoji verwijderd).
- Tenant-isolatie: niet geraakt; de tenant-context wordt na verificatie identiek gezet.
- Security: dit is een netto-verkleining van het aanvalsoppervlak. Geen enkel endpoint
  krijgt nieuwe toegang; twee endpoints (`/api/v1/ws/{channel}` en de room-variant)
  verliezen hun query-token-bron en gebruiken nu cookie/subprotocol/header.
- Regressie: 359 passed in de websocket/auth-set; architecture 396 passed; volledige
  integratiesuite eerder deze sessie 1731 passed / 0 failed.

## Restpunt

`tests/core/` bevat na deze fix nog 22 falende tests (328 passed), alle pre-existing
API-drift in zeven bestanden die niets met dit onderwerp te maken hebben
(`focus_builder_chat_agent` 9, `twin_worker` 6, `twin_models` 2, `pack_selector_endpoint`
2, en 3 losse). Die map valt buiten beide standaardsuites en is daarom nooit opgemerkt.
Apart te beleggen -- gemeld aan Rakesh.
