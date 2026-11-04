# BE-API-044: slowapi rate-limit call-contract op alle rate-limited endpoints

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-API-044 |
| Flow-ID | BE-FLW-054 |
| Sprint | OP-11 (integratie-baseline herstel) Dag 1 |
| Datum | 2026-07-31 |
| ADR-koppeling | ADR-014 (observability/rate-limit headers), ADR-033 (router-lagen) |
| Status | Geimplementeerd |
| Commits | `c3980499` (rode tests), `17024a42` (fix) |

## Probleem

`get_limiter()` bouwt elke slowapi `Limiter` met `headers_enabled=True`
(`src/core/middleware/rate_limiter.py:135`) -- in alle omgevingen, productie
inbegrepen. De slowapi-wrapper (`slowapi/extension.py:718-742`) doet daardoor bij
**elke** request twee dingen:

```python
request = kwargs.get("request", args[idx] if args else None)
if not isinstance(request, Request):
    raise Exception("parameter `request` must be an instance of ...Request")
...
response = await func(*args, **kwargs)
if not isinstance(response, Response):
    self._inject_headers(kwargs.get("response"), ...)   # zoekt op NAAM
else:
    self._inject_headers(response, ...)
```

Een endpoint met `@limiter.limit(...)` gooit dus een ongehandelde Exception --
HTTP 500 -- op elke request, tenzij:

1. het een parameter `request` heeft die een echte starlette `Request` is, en
2. het of een parameter met de **naam** `response` heeft, of zelf een
   `Response`-instantie retourneert.

**Aangetroffen situatie:** 10 van de 64 rate-limited endpoints schonden dit.
Zeven zaten verstopt achter rode integratietests die niemand draaide; drie hadden
geen enkele dekking. `POST /verify-token` (sync-server-authenticatie) was 100%
onbruikbaar: de Pydantic-body-param heette `request`, dus de isinstance-check
faalde nog voordat de handler liep.

## Oplossing

| Bestand | Endpoints | Wijziging |
| --- | --- | --- |
| `src/core/api/v1/orchestration/health_router.py` | `get_health_report`, `get_agent_health`, `record_health` | `response: Response` toegevoegd |
| `src/core/api/v1/orchestration/stats_router.py` | `get_stats` | idem + `Response`-import |
| `src/core/api/v1/orchestration/workflow_router.py` | `orchestrate_task`, `get_workflow_status`, `route_task` | idem + `Response`-import; lokale variabele `response` in `orchestrate_task` omgenoemd naar `task_response` (naamconflict) |
| `src/core/scheduling/api/integration_routes.py` | `connect_provider`, `trigger_sync` | `response: Response` toegevoegd |
| `src/core/api/auth/router_token.py` | `verify_token_endpoint` | body-param `request` -> `data`; echte `request: Request` + `response: Response` toegevoegd; `request.token` -> `data.token` (2x) |

**Waarom de parameter `response` moet heten:** slowapi zoekt hem op via
`kwargs.get("response")`. Een andere naam werkt niet, ook niet met de juiste
annotatie. Daarom is in `orchestrate_task` de lokale variabele omgenoemd en niet
de parameter.

**Waarom het JSON-contract van `/verify-token` niet verandert:** FastAPI leidt de
request-body af uit het Pydantic-model (`TokenVerifyRequest`), niet uit de
parameternaam. `data:` volgt bovendien de conventie van `refresh_token` en
`revoke_token_endpoint` in hetzelfde bestand.

**Niet aangeraakt:** `google_webhook` en `outlook_webhook`
(`src/core/scheduling/api/webhook_routes.py`) retourneren zelf een
`Response`-instantie en vallen daarmee in slowapi's tweede tak. Een eerdere
scanversie markeerde ze onterecht als kapot.

## Preventie

`tests/architecture/test_rate_limited_endpoints_slowapi_contract.py` scant met
AST alle `@limiter.limit`-endpoints in `src/` en faalt op elke nieuwe schending.
Drie tests:

1. `test_rate_limited_endpoints_can_receive_ratelimit_headers` -- `response`-param
   of Response-returnwaarde vereist.
2. `test_rate_limited_endpoints_expose_a_real_request_object` -- `request` moet een
   echte starlette Request zijn.
3. `test_scan_actually_finds_the_rate_limited_endpoints` -- bewaakt de scan tegen
   een vacuum-pass (minimaal 50 endpoints verwacht).

**Valkuil die de test expliciet afdekt:** de vergelijking op de return-annotatie
is **exact**. Een Pydantic-model dat toevallig `*Response` heet
(`HealthReportResponse`) is geen starlette `Response`; substring-matching liet
tijdens de triage twee kapotte endpoints stil passeren.

## Bewijs

| Gate | Resultaat |
| --- | --- |
| Rode tests voor de fix | 2 arch-tests + 2 verify-token-tests ROOD (`c3980499`); bewijs in de run: `Exception: parameter 'request' must be an instance of starlette.requests.Request` |
| Na de fix | 9/9 groen |
| Integratie orchestration | 20 failed -> 7 failed (13 weg, exact de voorspelling); resterende 7 = cluster B (403-governance), dag 2 |
| Gerichte set | 752 passed / 0 failed (incl. volledige architecture-suite) |
| Scheduling | 227 passed / 3 skipped |
| ruff | clean |
| pyright | 0 errors |
| mypy | 0 errors in de gewijzigde bestanden |

## Trainingssamenvatting

- Actor: Geauthenticeerde API-client (sync-server, frontend, of agenda-integratie)
- Voorwaarde: Het aangeroepen endpoint is voorzien van `@limiter.limit(...)` en de
  slowapi-limiter is geconfigureerd met `headers_enabled=True`.
- Actie: De client doet een request op een rate-limited endpoint, bijvoorbeeld
  `POST /verify-token`, `GET /api/v1/orchestrate/health` of
  `POST /api/v1/scheduling/integrations/{id}/sync`.
- Systeemreactie: De slowapi-wrapper controleert de limiet op basis van het echte
  `Request`-object, laat de handler lopen, en schrijft de `X-RateLimit-*`-headers
  op het `Response`-object dat als parameter is meegegeven (of op de
  Response-instantie die het endpoint zelf retourneert).
- Succesrespons: De normale statuscode van het endpoint (200/201/204) met
  `X-RateLimit-Limit`, `X-RateLimit-Remaining` en `X-RateLimit-Reset` in de headers.
- Foutrespons: Bij overschrijding van de limiet 429 met dezelfde headers. Bij een
  ongeldig of ingetrokken token blijft `/verify-token` 401 geven.
- Uitzonderingen: Endpoints die zelf een `Response`-instantie retourneren (zoals de
  Google- en Outlook-webhooks) hebben geen `response`-parameter nodig; slowapi
  gebruikt dan de returnwaarde.

## Restrisico

De 7 resterende 403-failures op de orchestration-endpoints zijn een aparte
oorzaak (cluster B) en staan op dag 2 van deze sprint. Ze zijn geen gevolg van
deze wijziging: voor de fix waren dezelfde 7 tests ook rood, alleen met een
andere foutmelding voor 13 andere tests.
