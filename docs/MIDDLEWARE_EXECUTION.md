# Middleware Execution Order

## Overview

This document specifies the order of middleware execution in the SanskritiSetu FastAPI application, along with the purpose and constraints of each middleware layer.

## Execution Order (Request → Response)

Middleware is executed in **reverse order of registration** (LIFO stack). Here's the canonical order:

1. **TenantMiddleware** — Extracts tenant_id from JWT, sets request context
2. **SecurityMiddleware** — Validates authentication, enforces security policies
3. **RateLimiterMiddleware** — Enforces rate limits per endpoint
4. **RequestIDMiddleware** — Attaches unique request ID for tracing
5. **CORSMiddleware** — Handles cross-origin requests
6. **GZipMiddleware** — Compresses responses
7. **OpenTelemetryMiddleware** — Traces requests to Jaeger
8. **ExceptionHandlerMiddleware** — Catches unhandled exceptions

### Response Order (Response ← Request)

Responses flow back through the stack in reverse order, allowing each middleware to modify/log the response before sending to client.

## Middleware Details

### 1. TenantMiddleware

**Purpose:** Extract `tenant_id` from JWT payload and populate `request.state.tenant_id`

**Behavior:**
- Reads JWT from Authorization header
- Calls `jwt_handler.verify_token()` 
- Extracts `tenant_id` claim
- Sets ContextVar for ORM auto-filtering

**Constraints:**
- MUST run before SecurityMiddleware (security middleware uses tenant context)
- MUST run before RateLimiter (rate limit keys are tenant-scoped)
- Skipped for PUBLIC_PREFIXES routes

**Failure Mode:** Returns 401 Unauthorized if JWT is invalid or missing

### 2. SecurityMiddleware

**Purpose:** Validate authentication and enforce security policies

**Behavior:**
- Checks SECURITY_KILL_SWITCH environment variable
- If kill switch is ON in development, allows all requests
- If kill switch is ON in production, blocks with 403
- Validates tenant isolation (user's tenant_id matches request tenant_id)
- Enforces RBAC scopes for protected endpoints

**Constraints:**
- MUST run after TenantMiddleware
- Skipped for PUBLIC_PREFIXES routes (e.g., /auth/login, /health)

**Failure Mode:** Returns 401 (auth failed) or 403 (policy violation)

### 3. RateLimiterMiddleware

**Purpose:** Enforce per-endpoint rate limits with tenant scoping

**Behavior:**
- Uses Redis for distributed rate limit tracking
- Key format: `ratelimit:{tenant_id}:{endpoint_path}`
- Checks slowapi decorator on each endpoint
- Returns 429 Too Many Requests when limit exceeded

**Constraints:**
- MUST run after TenantMiddleware (needs tenant_id)
- Different limits for read vs write operations
- GET endpoints: 60/min (read limits)
- POST/PUT/DELETE: 10/min (write limits)

**Failure Mode:** Returns 429 Too Many Requests

### 4. RequestIDMiddleware

**Purpose:** Attach unique request ID for distributed tracing

**Behavior:**
- Generates `X-Request-ID` header if not present
- Uses UUID v4 format
- Logs request ID with all subsequent logs

**Constraints:**
- Can run at any position (does not interact with auth/rate limiting)

**Failure Mode:** Never fails; generates new ID if missing

### 5. CORSMiddleware

**Purpose:** Handle cross-origin requests

**Behavior:**
- Allows requests from configured origins
- In development: allows localhost:*, 127.0.0.1:*
- In production: allows explicit origins only (no *)

**Constraints:**
- MUST run before response leaves the application
- Does not interact with auth/tenant logic

**Failure Mode:** Returns 403 CORS error for disallowed origins

### 6. GZipMiddleware

**Purpose:** Compress response bodies to reduce bandwidth

**Behavior:**
- Compresses responses > 500 bytes
- Only for text/* and application/json types
- Sets Content-Encoding: gzip header

**Constraints:**
- MUST run before response is sent to client
- Can run at any position in stack

**Failure Mode:** Silently skips compression on error (non-fatal)

### 7. OpenTelemetryMiddleware

**Purpose:** Trace requests to Jaeger for observability

**Behavior:**
- Creates spans for each request
- Records HTTP method, path, status code, latency
- Exports spans to Jaeger collector

**Constraints:**
- Skipped if Jaeger is not configured
- Non-blocking (uses async exports)

**Failure Mode:** Silently skips tracing on Jaeger error (non-fatal)

### 8. ExceptionHandlerMiddleware

**Purpose:** Catch unhandled exceptions and return structured error responses

**Behavior:**
- Catches any exception not handled by route handlers
- Returns 500 Internal Server Error
- Logs full stack trace with request context
- Never exposes internal error details to client

**Constraints:**
- MUST run last (catches all exceptions)
- Works with all previous middleware

**Failure Mode:** Returns 500 with generic error message

## Critical Constraints

### No Circular Dependencies

- TenantMiddleware cannot depend on SecurityMiddleware
- SecurityMiddleware cannot depend on TenantMiddleware after it runs (it uses the set tenant_id)

### Tenant Context Propagation

- TenantMiddleware MUST set `request.state.tenant_id` and ContextVar before any middleware uses it
- ORM hooks rely on ContextVar being set by TenantMiddleware

### Rate Limiting is Tenant-Scoped

- Rate limiter MUST run after TenantMiddleware
- Each tenant has separate rate limit bucket
- Prevents cross-tenant rate limit attacks

## Testing

All middleware is tested in `tests/integration/test_security_middleware_integration.py`:

- `TestMiddlewareExecutionOrder` — verifies correct execution order
- `TestTenantIsolation` — verifies tenant context is properly set
- `TestRateLimiting` — verifies per-tenant rate limiting
- `TestSecurityPolicies` — verifies kill switch and RBAC enforcement
- `TestPublicEndpoints` — verifies PUBLIC_PREFIXES bypass security

## Configuration

Middleware is registered in `src/core/api/middleware_registry.py`:

```python
def register_middleware(app: FastAPI) -> None:
    """Register all middleware in correct execution order."""
    app.add_middleware(OpenTelemetryMiddleware)
    app.add_middleware(GZipMiddleware)
    app.add_middleware(CORSMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(TenantMiddleware)
```

Note: Middleware is registered in REVERSE order because FastAPI adds them to a stack.

## Future Enhancements

- [ ] Add AsyncContextManager support for middleware cleanup
- [ ] Add middleware performance metrics (latency per middleware)
- [ ] Add configurable middleware skip list for testing
