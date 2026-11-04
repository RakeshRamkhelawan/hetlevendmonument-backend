# BE-MID-005: RateLimitMiddleware Pure ASGI Conversie

**Sprint:** Startup Pipeline Fix Dag 1  
**Datum:** 2026-06-05  
**Status:** APPROVED  

## Samenvatting

Conversie van `RateLimitMiddleware` van `BaseHTTPMiddleware` naar pure ASGI om hetzelfde `MissingGreenlet` risico te elimineren als `AuditLoggingMiddleware`.

## Context

- **Probleem (B-001b):** `RateLimitMiddleware` extend `BaseHTTPMiddleware` en doet DB calls (`db_manager.get_session()` + `TenantSubscriptionCache`). Dit had identiek `MissingGreenlet` risico, alleen minder vaak getroffen omdat niet elk endpoint rate-limited is.
- **Impact:** Potentiële 500 errors op rate-limited endpoints.

## Wijzigingen

### `src/core/middleware/rate_limit_middleware.py`

- Verwijderd: `from starlette.middleware.base import BaseHTTPMiddleware`
- Toegevoegd: `from starlette.types import ASGIApp, Message, Receive, Scope, Send`
- Toegevoegd: `from starlette.responses import JSONResponse`
- Class signature: `class RateLimitMiddleware(BaseHTTPMiddleware)` → `class RateLimitMiddleware:`
- Constructor: `super().__init__(app)` → `self.app = app`
- Entrypoint: `async def dispatch(self, request, call_next)` → `async def __call__(self, scope, receive, send)`
- Rate limit exceeded: in plaats van `raise RateLimitExceeded()`, stuur nu direct een `JSONResponse(status_code=429, ...)` via `send` en return. Dit voorkomt dat de exception door de ASGI stack propagaert zonder FastAPI exception handler.
- Non-HTTP bypass: `if scope["type"] != "http": await self.app(scope, receive, send); return`
- Headers: `send_wrapper` voegt `X-RateLimit-*` headers toe (analoog aan oude gedrag)

## Testdekking

- `tests/unit/middleware/test_rate_limit_middleware_pure_asgi.py` (4 tests)
  - Happy: request binnen quota retourneert 200 + headers
  - Unhappy: request over quota retourneert 429
  - Regression: async DB endpoint crasht niet

## Rollback

```bash
git revert <commit-hash>
```

## Acceptatiecriteria

- [x] Rate-limited endpoints retourneren correct 429 (niet 500)
- [x] `X-RateLimit-*` headers aanwezig in responses
- [x] Bestaande rate limit tests slagen

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
