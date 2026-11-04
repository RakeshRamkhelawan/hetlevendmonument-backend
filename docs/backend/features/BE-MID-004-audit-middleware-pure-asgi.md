# BE-MID-004: AuditLoggingMiddleware Pure ASGI Conversie

**Sprint:** Startup Pipeline Fix Dag 1  
**Datum:** 2026-06-05  
**Status:** APPROVED  

## Samenvatting

Conversie van `AuditLoggingMiddleware` van `BaseHTTPMiddleware` naar pure ASGI om `MissingGreenlet` errors te elimineren.

## Context

- **Probleem (B-001):** `AuditLoggingMiddleware` extend `BaseHTTPMiddleware`. Starlette 0.49.3 spawn endpoints in nieuwe anyio tasks zonder greenlet context. Async SQLAlchemy (`asyncpg`) gebruikt `greenlet` voor sync/async bridging → `MissingGreenlet` crash bij elke DB call.
- **Impact:** Elke API call die een `AsyncSession` gebruikt retourneerde 500. Audit logging (ADR-019 compliance) was volledig offline.

## Wijzigingen

### `src/core/middleware/audit_middleware.py`

- Verwijderd: `from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint`
- Toegevoegd: `from starlette.types import ASGIApp, Message, Receive, Scope, Send`
- Class signature: `class AuditLoggingMiddleware(BaseHTTPMiddleware)` → `class AuditLoggingMiddleware:`
- Constructor: `super().__init__(app)` → `self.app = app`
- Entrypoint: `async def dispatch(self, request, call_next)` → `async def __call__(self, scope, receive, send)`
- Non-HTTP bypass: `if scope["type"] != "http": await self.app(scope, receive, send); return`
- Response capture: `send_wrapper` pattern (analoog aan `TenantMiddleware`)
- Error handling: try/except rond `await self.app(...)` met audit logging bij exception + re-raise

## Tenant ID NOT NULL

- `RequestAuditLog.tenant_id`: `Mapped[str | None]` → `Mapped[str]` (`nullable=False`)
- `_extract_user_info()`: fallback naar `"0"` wanneer geen tenant in request state

## Testdekking

- `tests/unit/middleware/test_audit_middleware_pure_asgi.py` (5 tests)
  - Happy: request gelogd, excluded path niet gelogd, X-Request-ID header
  - Unhappy: error request gelogd
  - Regression: async DB endpoint crasht niet (MissingGreenlet)
- `tests/integration/middleware/test_missing_greenlet_middleware.py` (3 tests)
  - `/api/v1/board/queue`, `/api/v1/copilot/tasks`, POST `/api/v1/agents`

## Rollback

```bash
git revert <commit-hash>
alembic -c src/alembic.ini downgrade 3ee55ea8e623
```

## Acceptatiecriteria

- [x] `/api/v1/board/queue` retourneert 200 (niet 500)
- [x] Alle bestaande audit middleware tests slagen
- [x] Nieuwe MissingGreenlet regression tests slagen
- [x] `tenant_id` is NOT NULL in database

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
