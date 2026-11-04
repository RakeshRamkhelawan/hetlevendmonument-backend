# BE-SEC-042: geen token in de query string op websocket-paden (SEC-AGT-004 afgemaakt)

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-SEC-042 |
| Flow-ID | BE-FLW-056 |
| Sprint | OP-11 (integratie-baseline herstel), vervolgbevinding |
| Datum | 2026-07-31 |
| ADR-koppeling | ADR-003 (tenant identity via JWT), OWASP ASVS V7 |
| Status | Geimplementeerd |
| Commits | `8e36876f` (rode tests), `d12afc80` (fix) |

## Probleem

SEC-AGT-004 verwijderde het `?token=`-pad uit
`WebSocketAuthenticator._extract_token` -- OWASP ASVS V7 verbiedt sessie-identifiers in
query strings, omdat ze belanden in access logs, browsergeschiedenis, proxy logs en de
Referer-header.

Die hardening dekte echter alleen dat ene extractiepunt. Een AST-scan over `src/` vond
**zes** plekken die een token uit de query string bleven accepteren:

| Plek | Vorm | Consequentie |
| --- | --- | --- |
| `auth/dependencies.py:168` `get_current_user_ws` | `websocket.query_params.get("token")` | Hardening volledig omzeilbaar via deze dependency; bediende `/ws/copilot/signals` |
| `api/v1/focus_builder/ws_chat_router.py:31` | `token: str \| None = Query(None)` | SEC-011 had de cookie als voorkeur ingevoerd, maar het query-alternatief bleef bestaan |
| `api/v1/focus_builder/ws_status_router.py:31` | idem | idem |
| `api/v1/websocket/router.py:33` `websocket_endpoint` | idem, en het token werd echt gebruikt | Query-token was hier zelfs de enige auth-bron |
| `api/v1/websocket/router.py:105` `websocket_room_endpoint` | idem | idem |
| `api/swarm_websocket_endpoints.py:237` `swarm_stream_secure` | `token: Query(None)`, nooit gebruikt | Dood gewicht dat uitnodigde een token in de URL te zetten; auth liep al via `auth.authenticate(websocket)` |

**Waarom dit onopgemerkt bleef:** er stond een test die het onveilige gedrag
*vastlegde* in plaats van het te signaleren --
`test_ws_auth_query_param_backward_compat` asserteerde dat een geldig token in de URL
nog steeds inlogde, "voor transitional compatibility". Zolang die groen stond, leek er
niets aan de hand.

**Waarom handmatig zoeken niet volstond:** grep-werk vond 3 van de 6. De AST-scan
vond alle zes, inclusief twee endpoints in
`api/v1/websocket/router.py` en de dode swarm-parameter.

## Oplossing

- `auth/websocket_auth.py`: nieuwe publieke `extract_token(websocket)` als enig
  canoniek extractiepunt (cookie -> `Sec-WebSocket-Protocol` subprotocol ->
  `Authorization`-header), zodat call-sites geen eigen variant schrijven.
- `auth/dependencies.py`: `query_params.get("token")` verwijderd; alleen cookie en
  `Authorization`-header blijven over.
- `focus_builder` ws_chat + ws_status: `token`-parameter verwijderd; lezen uitsluitend de
  `access_token`-cookie.
- `swarm_websocket_endpoints.py`: ongebruikte parameter verwijderd (geen gedragswijziging).
- `api/v1/websocket/router.py`: parameter verwijderd; de extractie is verplaatst naar
  `websocket/manager.py::connect()`, die het token uit de websocket haalt zodra er geen
  wordt meegegeven.

**Waarom de extractie in de manager zit en niet in de router:** een import van
`WebSocketAuthenticator` in `core_api` bracht het DSM fan-out-budget van `core_api` op
**801** tegen een Grade A+ plafond van **800**
(`tests/architecture/test_dsm_grade_a_plus.py::test_fan_out_budget`). De manager heeft die
auth-afhankelijkheid al, dus daar kost het geen nieuwe architectuurrand. Dit is bovendien
de betere plek: de manager is de enige die het token nodig heeft.

**Frontend hoefde niet mee.** Alle drie de hooks authenticeren al via de cookie,
geverifieerd in de bron:
`useWebSocket.ts:76` ("Phase 6: Cookie-based auth"), `useFocusBuilderWS.ts:284` (stuurt
alleen `conversation_id` mee) en `useFlowStatusWebSocket.ts::buildWebSocketUrl` (geen
token in de URL).

## Preventie

`tests/architecture/test_websocket_no_query_param_token.py` scant met AST:

1. `test_no_websocket_route_accepts_a_query_param_token` -- geen `@router.websocket`-route
   mag een parameter met een tokennaam hebben (`token`, `access_token`, `jwt`,
   `auth_token`). `conversation_id`, `flow_id` en dergelijke mogen uiteraard wel in de
   query: dat zijn geen credentials.
2. `test_no_code_reads_a_token_from_query_params` -- geen module mag
   `...query_params.get("token")` doen.
3. `test_scan_actually_finds_websocket_routes` -- vangnet tegen een vacuum-pass
   (minimaal 10 routes verwacht).

## Trainingssamenvatting

- Actor: Browserclient of externe consumer die een websocket opent
- Voorwaarde: De client heeft een geldige sessie; het JWT zit in de HTTP-only
  `access_token`-cookie (canoniek), in het `Sec-WebSocket-Protocol` subprotocol, of in de
  `Authorization`-header.
- Actie: De client opent bijvoorbeeld `/ws/scheduling`,
  `/api/v1/focus-builder/ws/chat` of `/api/v1/ws/{channel}` -- zonder token in de URL.
- Systeemreactie: Het token wordt uit een van de drie toegestane bronnen gehaald,
  geverifieerd, en de tenant-context wordt gezet.
- Succesrespons: De verbinding wordt geaccepteerd; de eerste boodschap is een
  `connected`-frame met user_id en tenant_id.
- Foutrespons: Geen token -> sluiten met code 4001 of HTTP 401 (afhankelijk van het
  endpoint); ongeldig token -> 4003. Een token in de query string wordt **niet** meer
  gelezen en levert dus hetzelfde resultaat als geen token.
- Uitzonderingen: Een nieuwe websocket-route met een tokenparameter faalt de
  architecture-test; dat is bewust, want de stille variant hiervan bleef hier maanden
  onzichtbaar.

## Restrisico

Geen. De HTTP-kant is nagetrokken en blijkt al schoon:
`get_token_from_request` (`auth/dependencies.py:56-71`) leest uitsluitend de
`Authorization`-header, de `access_token`-cookie en de HTTPBearer-credentials -- geen
query-parameter. De docstring van `get_current_user` (`auth/dependencies.py:130`)
beschreef zichzelf nog als "Triple-Lock auth (header/cookie/query)"; dat was een
verouderde tekst en niet een werkend pad. Die tekst is meteen gecorrigeerd om te voorkomen dat iemand er later een
query-pad op baseert.
