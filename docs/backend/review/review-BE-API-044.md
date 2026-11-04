# Review: BE-API-044 — slowapi rate-limit call-contract (OP-11 dag 1)

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-API-044-slowapi-rate-limit-contract.md` |
| Reviewer | Fresh-eyes zelfreview (subagents niet toegestaan in deze sessie; expliciet gemeld aan Rakesh) |
| Datum | 2026-07-31 |
| Uitkomst | **APPROVED** |

---

## Controle tegen de code (geen aannames)

| Claim in spec | Verificatie | Oordeel |
| --- | --- | --- |
| `headers_enabled=True` in alle omgevingen | `src/core/middleware/rate_limiter.py:130-136` -- staat buiten de if/else voor productie vs development | Correct |
| slowapi eist `request` als starlette Request | `.venv/Lib/site-packages/slowapi/extension.py:722-726` gelezen: `if not isinstance(request, Request): raise Exception(...)` | Correct |
| slowapi zoekt `response` op naam | idem regel 735-742: `self._inject_headers(kwargs.get("response"), ...)` in de niet-Response-tak | Correct |
| 10 van 64 endpoints schonden dit | AST-scan (nu de architecture-test) telt 64 endpoints, 10 violations; lijst 1-op-1 gelijk aan de 3 gewijzigde routerbestanden + router_token + integration_routes | Correct |
| Webhooks zijn NIET kapot | `webhook_routes.py:57,113` retourneren `-> Response` en elk pad doet `return Response(status_code=200)` -- valt in slowapi's isinstance-tak | Correct; eerdere scanversie was fout, gecorrigeerd voor de fix |
| verify-token was 100% kapot | Rode test produceert exact `Exception: parameter 'request' must be an instance of starlette.requests.Request` | Correct, empirisch |
| JSON-contract `/verify-token` ongewijzigd | Body blijft `TokenVerifyRequest`; `response_model=TokenVerifyResponse` ongewijzigd; test asserteert `{"valid","tenantId","userId"}` | Correct |
| Bestaande type-contract-test blijft geldig | `tests/unit/api/auth/test_router_token_types.py` pint de **lokale** variabele `payload`; daarom is de body-param `data` genoemd en niet `payload` | Correct -- test groen |

## Bevindingen

Geen CRITICAL, geen HIGH.

MEDIUM (opgelost tijdens de review-ronde):
- R1 -- Eerste versie van de AST-scan matchte de return-annotatie via substring,
  waardoor `HealthReportResponse` als "retourneert een Response" gold. Dat gaf
  2 false negatives (`integration_routes.connect_provider`/`trigger_sync`) en
  2 false positives (de webhooks). De architecture-test vergelijkt nu exact en de
  spec documenteert de valkuil.
- R2 -- `orchestrate_task` had een lokale variabele `response`; pyright meldde
  3 echte errors (`reportAssignmentType`, `reportAttributeAccessIssue`,
  `reportReturnType`). Opgelost door de lokale om te noemen naar `task_response`,
  niet door de parameter anders te noemen (dat zou slowapi weer breken).

MINOR (geaccepteerd):
- R3 -- Pyright meldt `"response" is not accessed` als *hint* op de nieuwe
  parameters. Dat geldt al voor de bestaande `request`-parameters in dezelfde
  bestanden (zelfde patroon, bewust): slowapi leest ze via kwargs, niet de
  functiebody. Geen error, dus baseline blijft 0.

## Kwaliteitspoorten

- ruff: clean op alle 5 gewijzigde bronbestanden + beide nieuwe testbestanden.
- pyright: 0 errors (baseline gehaald; 54 warnings zijn ontbrekende optionele
  packages in deze omgeving).
- mypy: 0 errors in de gewijzigde bestanden (de 19 overige zitten in transitief
  meegeladen bestanden en horen bij de bekende SP-CI-001-backlog).
- ASCII: geen non-ASCII in code of tests.
- Security: geen nieuwe aanvalsoppervlakte. `/verify-token` werkt nu zoals bedoeld
  -- dat is een herstel van functionaliteit, geen verruiming van toegang; de
  401-paden (ongeldig, revoked, geen tenant) blijven ongewijzigd.
- Tenant-isolatie: niet geraakt; geen query- of tenant_id-pad gewijzigd.

## Restpunt

De 7 resterende 403-failures op deze endpoints (cluster B) zijn niet door deze
wijziging veroorzaakt -- ze waren voor de fix ook rood -- en staan gepland als
dag 2 van deze sprint.
