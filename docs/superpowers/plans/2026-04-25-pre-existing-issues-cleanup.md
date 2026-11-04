# Pre-Existing Issues Cleanup - Release Hardening Execution Plan

> For agentic workers: REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. This file is the canonical execution plan for this path; there is no separate source draft behind it.

**Goal:** Remove the release-blocking security and runtime risks identified in the audit, migrate the product to a browser-safe cookie session model, and prepare an externally reviewable change bundle with evidence-first validation.

**Architecture:** Execute in four ordered tracks. Track A closes live backend exploit paths (`?token=` HTTP auth, public setup bootstrap, ActivePieces tenant spoofing). Track B establishes a backend cookie-session contract and then migrates the frontend off token persistence and token-bearing websocket URLs. Track C reduces runtime cost and frontend boot overhead in isolated, parallelizable slices. Track D explicitly defers bootstrap-surface consolidation to an approved spec in `docs/superpowers/specs/2026-04-28-bootstrap-consolidation-spec.md` so implementation does not expand into design work mid-stream.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, pytest-asyncio, Playwright, Vitest, React Router, Vite, Prometheus middleware, secure httpOnly cookies, CSRF token validation, WebSocket browser auth.

**Parallelism note:** Phases 1, 2, 3, 4, 5, and 6 are sequential because each phase changes the trust boundary for the next. After Phase 6 is green, the runtime work is split into independent slices: 7a metrics, 7b lifespan, 7c frontend bootstrap, 7d route lazy loading, and 7e workflow sync deduplication. Phase 8 is not executable work in this plan and is blocked on the bootstrap spec.

**✅ MILESTONE ACHIEVED (2026-05-01):** Phases 1-7C are COMPLETE. All critical security hardening work is delivered. Backend cookie-session migration is active. Frontend token persistence removed. WebSocket auth migrated to cookie-based. Runtime optimizations (metrics, startup, bootstrap) are in place. 

**Remaining work:** Phases 7D-7E (optional performance refinements) and Phase 9 (final validation and external review bundle). Complete status documented in `docs/RELEASE_HARDENING_STATUS.md`.

**Current branch:** `fix/frontend-coverage-phase5` (contains unrelated workflow/frontend coverage changes alongside Phase 4-7C hardening diffs)

## Handover Summary

| Slice | Status | Reality |
|-------|--------|---------|
| Phase 0 | Partial | Preflight inventories and runtime-path classification were captured in repo memory, but the external review artifact bundle was not assembled yet. |
| Phase 1 | Complete | Normal HTTP `?token=` auth is removed. Header and cookie auth still work. WebSocket query-token compatibility is intentionally still present. |
| Phase 2 | Complete | Setup router exposure is gated by `APP_SETUP_MODE`, public allowlisting is narrowed, and bootstrap writes now target single-use `.env.bootstrap` instead of live `.env`. |
| Phase 3 | Complete | ActivePieces flow/connection ownership is now resolved from first-party records in repository and webhook layers. `src/core/activepieces/service.py` fallback behavior removed. Integration tests added for spoofed-tenant rejection. |
| Phase 7F local dev unblocker | Complete | `.env.local` generation, explicit compose project use, backend healthcheck restoration, and local runtime validation are complete. |
| Phase 4 | Complete | Backend cookie session contract implemented: login sets access_token + refresh_token cookies, refresh rotates access_token cookie, logout clears cookies. CSRF validation added to mutating auth endpoints. Integration tests cover happy/unhappy paths. |
| Phase 5 | Complete | Frontend token persistence removed from `TokenStorage`, `getHeaders`, `AuthContext`, `csrf.ts`, `tokenRefresh.ts`, and `client.ts`. Cookie-backed session flow is active. Unit tests green; e2e blocked by Playwright webServer port mismatch (5173 vs 5174). |
| Phase 6 | Complete | WebSocket cookie auth implemented. Frontend hooks (`useWebSocket`, `useHITLWebSocket`, `useFlowStatusWebSocket`, `useFocusBuilderWS`, `canvas.ts`) no longer emit `?token=`. Backend `get_current_user_ws` and `WebSocketAuthenticator` read `access_token` cookie first, with query-param fallback. Integration tests cover cookie precedence, rejection, and backward compat. |
| Phase 7A | Complete | Prometheus path normalization implemented. Dynamic segments (UUIDs, numeric IDs, hex IDs) are normalized to `{id}` before metric labeling. Slugs and static paths are preserved. |
| Phase 7B | Complete | Lifespan startup cost control implemented. Development mode skips database seeding when default tenant exists (`_default_tenant_exists` guard). Production always seeds. Unit tests cover skip behavior. |
| Phase 7C | Complete | Frontend bootstrap cleanup done. Removed unconditional `[DEBUG]` console.log noise from `main.tsx`. Replaced unsafe `innerHTML` injection fallbacks with safe DOM node creation. Unit tests verify no debug logs and no innerHTML usage. |
| Phases 7D-7E, and 9 | Open | No execution work has started yet. |

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `docs/superpowers/plans/2026-04-25-pre-existing-issues-cleanup.md` | Canonical release-hardening execution plan |
| Create | `docs/superpowers/specs/2026-04-28-bootstrap-consolidation-spec.md` | Approved design input for future bootstrap consolidation |
| Modify | `src/core/auth/dependencies.py` | Shared HTTP vs WebSocket credential extraction |
| Modify | `tests/unit/auth/test_dependencies.py` | RED/GREEN auth transport coverage |
| Modify | `src/core/api/public_endpoints.py` | Public route allowlist |
| Modify | `src/core/api/router_registry.py` | Canonical router registration gate |
| Modify | `src/core/api/setup_endpoints.py` | Setup endpoint behavior |
| Modify | `src/core/services/setup_service.py` | Bootstrap artifact writing and validation |
| Modify | `src/core/shared/config.py` | Setup-mode and cookie policy configuration anchor |
| Create | `tests/security/test_setup_endpoint_security.py` | Setup-surface security coverage |
| Modify | `src/core/api/webhooks/activepieces_handler.py` | Webhook tenant trust boundary |
| Modify | `src/core/activepieces/repositories.py` | First-party ownership lookup layer |
| Modify | `src/core/activepieces/service.py` | Tenant-to-project binding behavior |
| Modify | `tests/integration/test_webhook_security.py` | Webhook spoofing coverage |
| Modify | `tests/integration/test_webhook_endpoint_real.py` | Signed webhook integration coverage |
| Modify | `src/core/api/auth/router.py` | Login/refresh/revoke/current-user cookie contract |
| Create | `tests/integration/test_auth_cookie_session.py` | Cookie auth integration coverage |
| Modify | `frontend/src/services/auth/jwt.ts` | Browser token persistence removal |
| Modify | `frontend/tests/unit/TokenStorage.test.ts` | Frontend session regression coverage |
| Modify | `frontend/src/contexts/AuthContext.tsx` | Session restore/login/logout flow |
| Modify | `frontend/src/services/auth/tokenRefresh.ts` | Refresh strategy after cookie migration |
| Modify | `frontend/src/hooks/useWebSocket.ts` | Generic WebSocket auth transport |
| Modify | `frontend/src/hooks/useHITLWebSocket.ts` | HITL WebSocket auth transport |
| Modify | `frontend/src/lib/api/canvas.ts` | Canvas WebSocket transport |
| Modify | `frontend/src/hooks/__tests__/useFlowStatusWebSocket.test.ts` | Existing browser-auth websocket coverage |
| Modify | `frontend/src/hooks/__tests__/useFocusBuilderWS.test.ts` | Existing reconnect/expiry websocket coverage |
| Create | `frontend/src/hooks/__tests__/useHITLWebSocket.test.ts` | Focused HITL websocket coverage |
| Modify | `src/core/observability/metrics.py` | Prometheus path normalization |
| Create | `tests/unit/test_prometheus_middleware.py` | Metrics middleware coverage |
| Modify | `src/core/app_lifespan.py` | Startup cost controls |
| Create | `tests/unit/test_app_lifespan_startup.py` | Lifespan startup coverage |
| Modify | `frontend/src/main.tsx` | Frontend bootstrap cleanup |
| Modify | `frontend/src/App.tsx` | Route-level lazy loading |
| Modify | `frontend/tests/unit/lazy-loading.test.ts` | Lazy loading regression coverage |
| Modify | `frontend/src/components/workflow/WorkflowBuilder.tsx` | Duplicate sync send removal |

### Additional Files Already Changed During Execution

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/core/auth/token_extraction.py` | Shared header/cookie token normalization for the hardened HTTP auth path |
| Modify | `src/core/middleware/tenant_middleware.py` | Removes HTTP query-token fallback and reuses canonical extraction helpers |
| Modify | `tests/unit/test_auth_consolidation.py` | Regression coverage for FastAPI query-token rejection on normal HTTP routes |
| Modify | `tests/unit/test_tenant_middleware_coverage.py` | Middleware coverage for query-token rejection and quoted cookie acceptance |
| Modify | `tests/unit/api/test_setup_endpoints.py` | Updated unit coverage for setup-mode gating and reviewed artifact behavior |
| Create | `tests/unit/api/test_activepieces_webhook_tenant_binding.py` | Focused webhook tenant-binding regression coverage |
| Modify | `scripts/setup-dev-secrets.ps1` | Generates a complete `.env.local` for reproducible local dev compose |
| Modify | `quickstart.ps1` | Aligns supported local startup to `.env.local` and explicit compose project |
| Modify | `scripts/tasks.ps1` | Aligns supported local docker tasks to the same env/project contract |
| Modify | `src/scripts/fetch_logs.ps1` | Reads backend logs from the normalized local dev compose context |
| Modify | `docker-compose.dev.yml` | Restores backend healthchecks required by `service_healthy` dependencies |
| Modify | `DOCKER_SETUP.md` | Documents the normalized local dev startup contract |

---

## Review Checkpoint Artifact Template

Every phase checkpoint must produce the following artifact bundle for external review:

1. **Scope summary**: one paragraph with the precise threat model or runtime issue addressed.
2. **Changed files**: exact file list, no wildcards.
3. **RED evidence**: failing test names, exact command used, expected failure cause.
4. **GREEN evidence**: rerun of the same focused tests plus the narrow integration validation for the slice.
5. **Quality evidence**: exact `ruff`, `mypy`, `pre-commit`, `npm run type-check`, `npm run lint`, or build commands executed.
6. **Behavioral coverage**: one happy path, one unhappy path, and one user-observable behavior test for the slice.
7. **Residual risks**: anything intentionally deferred, including temporary compatibility behavior.

---

## Phase 0: Baseline, Design Freeze, and Preflight Audit

**Execution note (2026-04-30):** The initial transport, tenant, bootstrap, and runtime-path inventory was completed in-session and preserved in repo memory: `/memories/repo/phase1-structural-inventory-apr28.md`, `/memories/repo/phase1-http-token-hardening-apr28.md`, `/memories/repo/phase2-setup-surface-apr28.md`, and `/memories/repo/activepieces-dev-compose-env-apr30.md`. The remaining gap is packaging that evidence into the formal external-review checkpoint bundle this plan expects.

### Task 0A: Workspace and baseline verification [Partial]

**Files:**
- Read: `CLAUDE.md`
- Read: `docs/superpowers/plans/2026-04-11-agent-router.md`
- Read: `docs/superpowers/specs/2026-04-28-bootstrap-consolidation-spec.md`

- [ ] **Step 1: Create the review worktree in the project-approved location**

```bash
git worktree add .claude/worktrees/release-hardening develop
```

Expected: a clean worktree at `.claude/worktrees/release-hardening` checked out on `develop`.

- [ ] **Step 2: Capture the baseline for focused backend and frontend paths**

```bash
python -m pytest tests/unit/auth/test_dependencies.py -v
python -m pytest tests/integration/test_webhook_security.py -v --stepwise
cd frontend && npm run type-check
cd frontend && npm run test:unit:file -- tests/unit/TokenStorage.test.ts
```

Expected: exact pass/fail status recorded verbatim in the review artifact.

- [ ] **Step 3: Commit the baseline notes only after they are written into the artifact bundle**

No production edits happen before the baseline artifact exists.

### Task 0B: Preflight inventory for transport and tenant pitfalls [Partial]

**Files:**
- Read: `src/**`
- Read: `frontend/src/**`
- Read: `tests/**`

- [ ] **Step 1: Inventory all frontend and backend `?token=` usages before any auth change**

```bash
git grep -nF "?token=" -- src frontend/src tests
git grep -nE "URLSearchParams.*token|searchParams\.set\(['\"]token['\"]|params\.token" -- src frontend/src tests
```

Expected: exact list of HTTP and WebSocket token transport paths captured in the artifact.

- [ ] **Step 2: Inventory all `X-Tenant-ID` readers and tenant fallbacks**

```bash
git grep -nE 'request\.headers\.get\(.*[Tt]enant|Header\(.*[Tt]enant|query_params\.get\(.*tenant' -- src tests
git grep -nE '"X-Tenant-ID"|x-tenant-id' -- src frontend/src tests
```

Expected: all client-controlled tenant sources are enumerated before Phase 1 begins.

- [ ] **Step 3: Record rate-limiter and alternate JWT verification residual risks**

This step is mandatory because `CLAUDE.md` lists tenant header fallbacks and multiple JWT verification paths as known pitfalls.

- [ ] **Step 4: Inventory non-browser auth consumers and browser test scaffolding before Phase 4**

Required reads and checks:

- `frontend/tests/e2e/auth.spec.ts`
- any Playwright auth helpers or mock setup files that currently seed localStorage-backed auth
- any API clients, scripts, or integrations that still require token-in-body responses

Expected: the artifact states whether Phase 4 can move to cookies-only for browser flows without breaking non-browser consumers or the existing Playwright suite.

### Task 0C: Audit existing session, CSRF, and bootstrap behavior before RED tests are written [Partial]

**Files:**
- Modify: review artifact only
- Read: `src/core/api/public_endpoints.py`
- Read: `src/core/api/auth/router.py`
- Read: `frontend/src/services/csrf.ts`
- Read: `frontend/src/services/__tests__/csrf.test.ts`
- Read: `src/core/middleware/websocket_cors.py`

- [ ] **Step 1: Audit the existing CSRF implementation and freeze the cookie policy around it**

Validate the current frontend token fetch flow in `frontend/src/services/csrf.ts`, the backend `/api/v1/auth/csrf-token` route, and Redis-backed validation before Phase 4 begins. Document and approve the following:

- cookie names for access and refresh
- `HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain`, and max-age semantics
- localhost/development versus production behavior for `Secure`
- refresh rotation behavior and replay handling
- whether all auth-mutating endpoints require the existing CSRF contract
- whether the existing CSRF contract remains valid once cookies, `SameSite`, and browser-auth WebSockets change
- WebSocket origin and browser-auth policy after cookie migration

- [ ] **Step 1a: Freeze the session model**

Unless explicitly changed by a future approved design, sessions remain stateless JWTs carried in secure cookies, with revocation handled by expiry and refresh rotation rather than a new database-backed session table.

- [ ] **Step 2: Freeze setup-mode policy**

Document that production setup/bootstrap is disabled by default and only enabled by explicit `APP_SETUP_MODE=true`.

- [ ] **Step 3: Record vendor-scope exclusion**

Explicitly state that `activepieces` and `activepieces-repo` vendor trees remain out of scope; only first-party integration code is covered.

---

## Phase 1: HTTP Token Transport Hardening

**Status:** Complete.

**What actually changed:** `src/core/auth/dependencies.py` now uses canonical header/cookie-only HTTP extraction, `src/core/auth/token_extraction.py` centralizes token normalization, and `src/core/middleware/tenant_middleware.py` no longer trusts HTTP query tokens. Additional regression coverage was added in `tests/unit/test_auth_consolidation.py` and `tests/unit/test_tenant_middleware_coverage.py`.

**Focused validation that passed:** `tests/unit/auth/test_dependencies.py`, `tests/unit/test_auth_consolidation.py -k 'query_param'`, and `tests/unit/test_tenant_middleware_coverage.py -k 'query_string_token_returns_401 or access_token_cookie_allows_request'`.

**Residual risk:** `get_current_user_ws` still accepts WebSocket query tokens by design until Phase 6 removes that temporary compatibility path.

### Task 1: Split HTTP token extraction from WebSocket token extraction [Implemented]

**Files:**
- Modify: `src/core/auth/dependencies.py`
- Modify: `tests/unit/auth/test_dependencies.py`

- [ ] **Step 1: Write failing tests for HTTP rejection of query-string tokens**

Marker: `@pytest.mark.unit`

Add five focused tests with explicit markers:

- one happy path proving Authorization header auth still works
- one happy path proving `access_token` cookie auth still works
- one unhappy path proving normal HTTP requests with only `?token=` return `401`
- one user-behavior test proving browser session restore still works when cookie auth is present
- one compatibility test proving `get_current_user_ws` still accepts WebSocket query tokens until Phase 6 removes that transport

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/unit/auth/test_dependencies.py -v
```

Expected: the new HTTP query-token rejection test fails for the expected reason, not due to setup errors.

- [ ] **Step 3: Implement the smallest change in `src/core/auth/dependencies.py`**

Requirements:

- `get_token_from_request` must only accept Authorization header or `access_token` cookie for `Request`
- `get_current_user_ws` remains the only place where WebSocket query-param extraction is allowed
- do not change `_get_user_from_token` in this task

- [ ] **Step 4: Verify GREEN on the same file first**

```bash
python -m pytest tests/unit/auth/test_dependencies.py -v
```

- [ ] **Step 5: Run the narrowest affected integration check**

```bash
python -m pytest tests/integration/test_workflow_execution.py -v --stepwise
```

- [ ] **Step 6: Run quality checks**

```bash
ruff check src/core/auth/dependencies.py
mypy src/core/auth/dependencies.py
pre-commit run --files src/core/auth/dependencies.py tests/unit/auth/test_dependencies.py
```

---

## Phase 2: Setup Endpoint Lockdown

**Status:** Complete.

**What actually changed:** `APP_SETUP_MODE` and reviewed artifact helpers were added to `src/core/shared/config.py`, setup route registration and public exposure were gated in `src/core/api/router_registry.py` and `src/core/api/public_endpoints.py`, `src/core/services/setup_service.py` now writes only to single-use `.env.bootstrap`, and endpoint/test behavior was updated in `src/core/api/setup_endpoints.py`, `tests/security/test_setup_endpoint_security.py`, and `tests/unit/api/test_setup_endpoints.py`.

**Focused validation that passed:** `tests/security/test_setup_endpoint_security.py`, `tests/unit/api/test_setup_endpoints.py`, plus focused `ruff` and `mypy` on the touched Python files.

**Residual risk:** Bootstrap consolidation remains explicitly deferred. Do not reopen it from this plan.

### Task 2A: Add setup-surface RED coverage, including newline corruption and production denial [Implemented]

**Files:**
- Create: `tests/security/test_setup_endpoint_security.py`
- Read: `src/core/api/setup_endpoints.py`
- Read: `src/core/services/setup_service.py`

- [ ] **Step 1: Write failing tests for all setup risks**

Marker: `@pytest.mark.security`

Required coverage:

- unhappy path: `POST /api/v1/setup/init` is not publicly reachable in normal runtime
- unhappy path: setup router is absent or denied unless `APP_SETUP_MODE=true`
- unhappy path: setup writes do not append to live `.env` in production mode
- unhappy path: multi-key bootstrap writes use real line separators, not literal `\\n`
- user-behavior test: bootstrap mode can still perform reviewed setup behavior when explicitly enabled in a controlled environment

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/security/test_setup_endpoint_security.py -v --stepwise
```

### Task 2B: Gate registration and public exposure atomically [Implemented]

**Files:**
- Modify: `src/core/shared/config.py`
- Modify: `src/core/api/router_registry.py`
- Modify: `src/core/api/public_endpoints.py`

- [ ] **Step 1: Add `APP_SETUP_MODE` to the shared configuration path**

The flag must default to disabled.

- [ ] **Step 2: Gate router registration before changing the allowlist**

`src/core/api/router_registry.py` must not register the setup router when `APP_SETUP_MODE` is false.

- [ ] **Step 3: Remove `/api/v1/setup/` from the public allowlist in the same commit**

This is intentionally atomic to avoid the broken middle state where setup remains registered but is impossible to use safely.

### Task 2C: Replace live `.env` mutation with reviewed bootstrap artifact behavior [Implemented]

**Files:**
- Modify: `src/core/api/setup_endpoints.py`
- Modify: `src/core/services/setup_service.py`

- [ ] **Step 1: Keep the endpoint denied outside setup mode**

Return a consistent `404` or `403` when setup mode is disabled.

- [ ] **Step 2: Replace `.env` append behavior**

Requirements:

- never write to live `.env` from the public runtime path
- write only to a reviewed bootstrap artifact such as `.env.bootstrap`
- use actual newline separators, not literal `\\n`
- preserve `validate_openai_key` as a narrow helper

- [ ] **Step 3: Verify GREEN on the setup slice**

```bash
python -m pytest tests/security/test_setup_endpoint_security.py -v --stepwise
python -m pytest tests/unit/auth/test_dependencies.py -v
```

- [ ] **Step 4: Run quality checks**

```bash
ruff check src/core/shared/config.py src/core/api/router_registry.py src/core/api/public_endpoints.py src/core/api/setup_endpoints.py src/core/services/setup_service.py
mypy src/core/shared/config.py src/core/api/router_registry.py src/core/api/public_endpoints.py src/core/api/setup_endpoints.py src/core/services/setup_service.py
pre-commit run --files src/core/shared/config.py src/core/api/router_registry.py src/core/api/public_endpoints.py src/core/api/setup_endpoints.py src/core/services/setup_service.py tests/security/test_setup_endpoint_security.py
```

---

## Phase 3: ActivePieces Tenant Binding Hardening

**Status:** Partial.

**What actually changed:** `src/core/activepieces/repositories.py` gained first-party ownership lookups by flow and connection reference, `src/core/api/webhooks/activepieces_handler.py` now resolves tenant authority from stored bindings instead of payload authority, and `tests/unit/api/test_activepieces_webhook_tenant_binding.py` captures the spoofed-tenant regression.

**What is still open:** remove the first-project fallback in `src/core/activepieces/service.py`, normalize the plan-level integration coverage in `tests/integration/test_webhook_security.py` and `tests/integration/test_webhook_endpoint_real.py`, and then rerun the focused live-stack checks.

**Validation already completed:** focused unit tests passed, earlier live webhook validation against the running stack passed, and the local dev stack is now stable enough to continue this phase.

**Residual risk:** `ExecutionEvent.tenant_id` is still present in payload shapes and must remain diagnostic only.

### Task 3A: Write RED tests for server-side tenant ownership resolution [Partial]

**Files:**
- Modify: `tests/integration/test_webhook_security.py`
- Modify: `tests/integration/test_webhook_endpoint_real.py`

- [ ] **Step 1: Add failing tests for spoofed payload tenant IDs**

Required coverage:

- unhappy path: signed webhook with mismatched payload `tenant_id` is rejected or ignored
- unhappy path: unknown `project_id` or `flow_id` does not produce cross-tenant updates
- happy path: owned `project_id` plus `flow_id` resolves to the correct tenant
- user-behavior test: tenant A cannot observe tenant B side effects from a valid webhook event

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/integration/test_webhook_security.py -v --stepwise
```

### Task 3B: Move trust from payload tenant to first-party lookup [Partial]

**Files:**
- Modify: `src/core/activepieces/repositories.py`
- Modify: `src/core/api/webhooks/activepieces_handler.py`
- Modify: `src/core/activepieces/service.py`

- [ ] **Step 1: Add repository lookup for tenant ownership**

The lookup must resolve ownership from first-party records using `ap_flow_id`, `project_id`, or equivalent local bindings.

- [ ] **Step 2: Keep `tenant_id` in webhook models only if it is diagnostic-only**

If `ExecutionEvent.tenant_id` remains, document and test that it is used only for mismatch logging or rejection, never as authority.

- [ ] **Step 3: Remove first-project fallback behavior from the service layer**

`_get_or_create_project_for_tenant` and `_get_project_for_tenant` must not silently bind tenants to the first upstream project.

- [ ] **Step 4: Verify GREEN on the same integration slice first**

```bash
python -m pytest tests/integration/test_webhook_security.py -v --stepwise
python -m pytest tests/integration/test_webhook_endpoint_real.py -v --stepwise
```

- [ ] **Step 5: Run quality checks**

```bash
ruff check src/core/activepieces/repositories.py src/core/api/webhooks/activepieces_handler.py src/core/activepieces/service.py
mypy src/core/activepieces/repositories.py src/core/api/webhooks/activepieces_handler.py src/core/activepieces/service.py
pre-commit run --files src/core/activepieces/repositories.py src/core/api/webhooks/activepieces_handler.py src/core/activepieces/service.py tests/integration/test_webhook_security.py tests/integration/test_webhook_endpoint_real.py
```

---

## Phase 4: Backend Cookie Session Contract

### Task 4A: RED tests for login, refresh, revoke, current-user, audit, and CSRF semantics

**Files:**
- Create: `tests/integration/test_auth_cookie_session.py`
- Read: `src/core/api/auth/router.py`
- Read: `src/core/auth/dependencies.py`

- [ ] **Step 1: Write failing integration tests for the cookie contract**

Marker: `@pytest.mark.integration`

Required coverage:

- happy path: login sets reviewed cookies and user can fetch current-user via cookie auth
- unhappy path: mutating request without the agreed CSRF signal is rejected once cookie auth is active
- happy path: refresh rotates the cookie-backed session according to the approved design
- unhappy path: revoked or cleared session cookie no longer authenticates
- user-behavior test: browser session restore works without local token storage
- audit behavior test: any new audit write in auth flows uses `async with best_effort(...)`

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/integration/test_auth_cookie_session.py -v --stepwise
```

### Task 4B: Implement the backend cookie contract

**Files:**
- Modify: `src/core/api/auth/router.py`
- Modify: `src/core/auth/dependencies.py`

- [ ] **Step 1: Write and clear secure httpOnly cookies on login, refresh, and revoke**

Use the Phase 0 design freeze for exact cookie semantics.

- [ ] **Step 1a: Apply the existing CSRF contract consistently to auth-mutating endpoints**

Ensure login, refresh, revoke, and any other state-changing auth routes in `src/core/api/auth/router.py` align with the audited CSRF flow rather than creating a second CSRF mechanism.

- [ ] **Step 2: Keep HTTP auth limited to header or cookie**

Do not reintroduce query transport into the normal HTTP path.

- [ ] **Step 3: Verify GREEN on the same focused integration tests**

```bash
python -m pytest tests/integration/test_auth_cookie_session.py -v --stepwise
python -m pytest tests/unit/auth/test_dependencies.py -v
```

- [ ] **Step 4: Run quality checks**

```bash
ruff check src/core/api/auth/router.py src/core/auth/dependencies.py
mypy src/core/api/auth/router.py src/core/auth/dependencies.py
pre-commit run --files src/core/api/auth/router.py src/core/auth/dependencies.py tests/integration/test_auth_cookie_session.py tests/unit/auth/test_dependencies.py
```

---

## Phase 5: Frontend Session Migration

### Task 5: Remove token persistence from the browser session path

**Files:**
- Modify: `frontend/src/services/auth/jwt.ts`
- Modify: `frontend/src/contexts/AuthContext.tsx`
- Modify: `frontend/src/services/auth/tokenRefresh.ts`
- Modify: `frontend/src/services/csrf.ts`
- Modify: `frontend/src/services/__tests__/csrf.test.ts`
- Modify: `frontend/tests/unit/TokenStorage.test.ts`
- Modify: `frontend/tests/e2e/auth.spec.ts`

- [ ] **Step 1: Write failing frontend tests for the new desired state**

Required coverage:

- unhappy path: access and refresh tokens are not persisted in localStorage for normal auth flow
- happy path: session restore succeeds via backend cookie auth
- unhappy path: logout clears client session state without leaving token artifacts behind
- user-behavior test: refreshed session remains usable after page reload
- unhappy path: `frontend/src/services/csrf.ts` no longer depends on `TokenStorage` or injects bearer auth once cookie mode is active

- [ ] **Step 2: Verify RED**

```bash
cd frontend && npm run test:unit:file -- tests/unit/TokenStorage.test.ts
cd frontend && npm run test:unit:file -- src/services/__tests__/csrf.test.ts
```

- [ ] **Step 3: Implement the smallest browser-side migration**

Requirements:

- `TokenStorage` stops being the source of truth for bearer tokens
- `AuthContext` restores session through `authApi.getCurrentUser` with browser cookies
- `tokenRefresh.ts` no longer depends on persisted `refresh_token`
- `frontend/src/services/csrf.ts` no longer reads tokens from browser storage or sends Authorization headers for the browser session flow
- existing Playwright auth scaffolding is updated away from localStorage assumptions

- [ ] **Step 4: Verify GREEN on the same focused tests**

```bash
cd frontend && npm run test:unit:file -- tests/unit/TokenStorage.test.ts
cd frontend && npm run test:unit:file -- src/services/__tests__/csrf.test.ts
cd frontend && npm run type-check
```

- [ ] **Step 5: Run quality checks**

```bash
cd frontend && npm run lint
cd frontend && npm run type-check
```

---

## Phase 6: WebSocket Auth Migration

### Task 6A: Remove token-bearing WebSocket URLs from the frontend

**Files:**
- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `frontend/src/hooks/useHITLWebSocket.ts`
- Modify: `frontend/src/lib/api/canvas.ts`
- Modify: `frontend/src/hooks/__tests__/useFlowStatusWebSocket.test.ts`
- Modify: `frontend/src/hooks/__tests__/useFocusBuilderWS.test.ts`
- Create: `frontend/src/hooks/__tests__/useHITLWebSocket.test.ts`

- [ ] **Step 1: Write failing tests proving URLs must not expose bearer tokens**

Marker: frontend unit tests

Required coverage:

- unhappy path: generic WebSocket URL builder does not emit `?token=`
- unhappy path: HITL WebSocket URL builder does not emit `?token=`
- unhappy path: canvas WebSocket transport does not emit `?token=`
- happy path: reconnect and expiry behavior from existing tests stays intact
- user-behavior test: browser-authenticated WebSocket reconnect succeeds without surfacing token text in the URL

- [ ] **Step 2: Verify RED**

```bash
cd frontend && npm run test:unit:file -- src/hooks/__tests__/useFlowStatusWebSocket.test.ts
cd frontend && npm run test:unit:file -- src/hooks/__tests__/useFocusBuilderWS.test.ts
cd frontend && npm run test:unit:file -- src/hooks/__tests__/useHITLWebSocket.test.ts
```

- [ ] **Step 3: Implement the smallest transport change**

Document any surface that cannot yet use cookie-based browser auth as an explicit exception in the checkpoint artifact.

- [ ] **Step 4: Verify GREEN and run quality checks**

```bash
cd frontend && npm run test:unit:file -- src/hooks/__tests__/useFlowStatusWebSocket.test.ts
cd frontend && npm run test:unit:file -- src/hooks/__tests__/useFocusBuilderWS.test.ts
cd frontend && npm run test:unit:file -- src/hooks/__tests__/useHITLWebSocket.test.ts
cd frontend && npm run lint
cd frontend && npm run type-check
```

### Task 6B: Backend WebSocket cookie auth and origin enforcement

**Files:**
- Modify: `src/core/auth/websocket_auth.py`
- Modify: `src/core/auth/dependencies.py`
- Modify: `src/core/middleware/websocket_cors.py`
- Create: `tests/integration/test_websocket_cookie_auth.py`

- [ ] **Step 1: Write failing integration tests for WebSocket cookie auth and allowed origins**

Marker: `@pytest.mark.integration`

Required coverage:

- unhappy path: Origin outside the allowlist is rejected
- unhappy path: handshake without auth cookie is rejected
- happy path: valid auth cookie plus allowed Origin is accepted
- unhappy path: query-token WebSocket auth is rejected once cookie mode is fully active
- user-behavior test: browser-authenticated reconnect succeeds only from an allowed Origin

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/integration/test_websocket_cookie_auth.py -v --stepwise
```

- [ ] **Step 3: Implement the smallest backend changes using the existing middleware as the starting point**

Requirements:

- `src/core/middleware/websocket_cors.py` remains the origin-enforcement anchor, not a parallel replacement
- `src/core/auth/websocket_auth.py` and `src/core/auth/dependencies.py` align with cookie-based browser auth for WebSockets
- any temporary exception for query-token compatibility is explicitly documented and time-bounded

- [ ] **Step 4: Verify GREEN on the same integration slice first**

```bash
python -m pytest tests/integration/test_websocket_cookie_auth.py -v --stepwise
python -m pytest tests/integration/test_workflow_execution.py -v --stepwise
```

- [ ] **Step 5: Run quality checks**

```bash
ruff check src/core/auth/websocket_auth.py src/core/auth/dependencies.py src/core/middleware/websocket_cors.py
mypy src/core/auth/websocket_auth.py src/core/auth/dependencies.py src/core/middleware/websocket_cors.py
pre-commit run --files src/core/auth/websocket_auth.py src/core/auth/dependencies.py src/core/middleware/websocket_cors.py tests/integration/test_websocket_cookie_auth.py
```

---

## Phase 7A: Prometheus Path Normalization

### Task 7A: Bound endpoint cardinality in middleware metrics

**Files:**
- Modify: `src/core/observability/metrics.py`
- Create: `tests/unit/test_prometheus_middleware.py`

- [ ] **Step 1: Write RED tests for dynamic path normalization**

Marker: `@pytest.mark.unit`

- [ ] **Step 2: Verify RED with `python -m pytest tests/unit/test_prometheus_middleware.py -v --stepwise`**
- [ ] **Step 3: Implement normalization for IDs and UUID-like segments before labeling metrics**
- [ ] **Step 4: Verify GREEN and run exact quality commands**

```bash
python -m pytest tests/unit/test_prometheus_middleware.py -v --stepwise
ruff check src/core/observability/metrics.py tests/unit/test_prometheus_middleware.py
mypy src/core/observability/metrics.py
pre-commit run --files src/core/observability/metrics.py tests/unit/test_prometheus_middleware.py
```

## Phase 7B: Lifespan Startup Cost Control

### Task 7B: Prevent heavy seed and verification work from rerunning unnecessarily

**Files:**
- Modify: `src/core/app_lifespan.py`
- Create: `tests/unit/test_app_lifespan_startup.py`

- [ ] **Step 1: Write RED tests for development skip behavior and one-time execution rules**

Marker: `@pytest.mark.unit`

- [ ] **Step 2: Verify RED with `python -m pytest tests/unit/test_app_lifespan_startup.py -v --stepwise`**
- [ ] **Step 3: Implement the smallest skip/guard logic without redesigning the whole lifespan layer**
- [ ] **Step 4: Verify GREEN and run exact quality commands**

```bash
python -m pytest tests/unit/test_app_lifespan_startup.py -v --stepwise
ruff check src/core/app_lifespan.py tests/unit/test_app_lifespan_startup.py
mypy src/core/app_lifespan.py
pre-commit run --files src/core/app_lifespan.py tests/unit/test_app_lifespan_startup.py
```

## Phase 7C: Frontend Bootstrap Cleanup

### Task 7C: Remove debug-heavy startup behavior from `main.tsx`

**Files:**
- Modify: `frontend/src/main.tsx`
- Create or modify: `frontend/tests/unit/main.bootstrap.test.tsx`

- [ ] **Step 1: Write focused frontend tests for bootstrap behavior**

Required coverage:

- happy path: `main.tsx` renders in normal mode without debug-log noise
- unhappy path: bootstrap failure does not fall back to unsafe `innerHTML` injection
- user-behavior test: the rendered fallback UI remains safe and user-visible during bootstrap failure

- [ ] **Step 2: Verify RED with `cd frontend && npm run test:unit:file -- tests/unit/main.bootstrap.test.tsx`**
- [ ] **Step 3: Remove unconditional debug logging and fatal `innerHTML` rendering from the normal path**
- [ ] **Step 4: Verify GREEN and run exact quality commands**

```bash
cd frontend && npm run test:unit:file -- tests/unit/main.bootstrap.test.tsx
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm run type-check
```

## Phase 7D: Route-Level Lazy Loading

### Task 7D: Introduce route-level code splitting for low-frequency routes first

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/unit/lazy-loading.test.ts`

- [ ] **Step 1: Write RED tests or extend existing lazy-loading coverage**
- [ ] **Step 2: Verify RED with `cd frontend && npm run test:unit:file -- tests/unit/lazy-loading.test.ts`**
- [ ] **Step 3: Convert low-frequency routes to `React.lazy` boundaries while keeping explicitly approved entry chunks eager**
- [ ] **Step 4: Verify GREEN and run exact quality commands**

```bash
cd frontend && npm run test:unit:file -- tests/unit/lazy-loading.test.ts
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm run type-check
```

## Phase 7E: WorkflowBuilder Sync Deduplication

### Task 7E: Emit each local `node_add` operation once

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowBuilder.tsx`
- Create or modify: `frontend/src/components/workflow/__tests__/WorkflowBuilder.sync.test.tsx`

- [ ] **Step 1: Write a failing test proving a local node creation emits one logical sync event**
- [ ] **Step 2: Verify RED on that focused test file**
- [ ] **Step 3: Remove the duplicate emission path between `handleChange` and the follow-up effect**
- [ ] **Step 4: Verify GREEN and run exact quality commands**

```bash
cd frontend && npm run test:unit:file -- src/components/workflow/__tests__/WorkflowBuilder.sync.test.tsx
cd frontend && npm run lint
cd frontend && npm run type-check
```

## Phase 7F: Local Dev Compose Reproducibility (Unplanned Unblocker)

### Task 7F: Normalize local dev startup so real integration testing is reproducible [Complete]

**Why this was added:** Phase 3 live validation was blocked by a non-reproducible local stack. ActivePieces required secrets that local bootstrap did not generate, supported entrypoints used different env files and project names, the dev override disabled the backend healthcheck while dependents still required `service_healthy`, and the existing dev Postgres volume had a populated schema with an empty `alembic_version` table.

**Files:**

- Modify: `scripts/setup-dev-secrets.ps1`
- Modify: `quickstart.ps1`
- Modify: `scripts/tasks.ps1`
- Modify: `src/scripts/fetch_logs.ps1`
- Modify: `docker-compose.dev.yml`
- Modify: `DOCKER_SETUP.md`

- [x] **Step 1: Make `.env.local` the canonical supported local dev compose env source**
- [x] **Step 2: Generate the missing ActivePieces secrets and compose keys from `scripts/setup-dev-secrets.ps1`**
- [x] **Step 3: Align supported dev entrypoints to explicit `-p sanskritisetuorg --env-file .env.local`**
- [x] **Step 4: Re-enable backend healthchecks in dev so `service_healthy` dependencies can start**
- [x] **Step 5: Validate backend and ActivePieces against the live compose stack**

**Validation actually completed:**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-dev-secrets.ps1 -Force
docker compose -p sanskritisetuorg --env-file .env.local -f docker-compose.yml -f docker-compose.dev.yml up -d
Invoke-WebRequest -Uri http://127.0.0.1:8110/docs -UseBasicParsing -TimeoutSec 60
Invoke-WebRequest -Uri http://127.0.0.1:8090 -UseBasicParsing -TimeoutSec 30
```

Observed result:

- backend `/docs` returned `200`
- ActivePieces `/` returned `200`
- `sanskritisetu_network` labels resolved to project `sanskritisetuorg`

**Operational note:** On this workstation, backend startup still failed once after the compose/env fixes because the existing dev Postgres volume already contained a populated schema and an empty `alembic_version` table. The one-time local repair was:

```powershell
docker exec sanskritisetu_postgres psql -U postgres -d sanskritisetu -c "SELECT COUNT(*) FROM alembic_version;"
docker exec sanskritisetu_postgres psql -U postgres -d sanskritisetu -c "INSERT INTO alembic_version (version_num) VALUES ('20260427_create_conversations');"
```

Do not rerun that blindly. Only use it when the schema already exists and `COUNT(*) FROM alembic_version` is `0`.

---

## Phase 8: Bootstrap Consolidation Is Explicitly Deferred

### Task 8: Do not implement bootstrap consolidation from this plan

**Files:**
- Read: `docs/superpowers/specs/2026-04-28-bootstrap-consolidation-spec.md`

- [ ] **Step 1: Treat bootstrap consolidation as out of execution scope here**

No production bootstrap refactor happens from this plan.

- [ ] **Step 2: If a reviewer approves bootstrap consolidation, create a new dedicated implementation plan from the approved spec**

This prevents open-ended discovery inside an execution plan.

---

## Phase 9: Final Release Gate and External Review Bundle

### Task 9: Run the release gate with full project-required verification

**Files:**
- Modify: external review artifact only

- [ ] **Step 1: Re-run the focused backend and frontend phase validations that changed behavior**

All full pytest runs must use `--stepwise`.

- [ ] **Step 2: Run integration validation against the real backend after each completed phase and again here**

No mock-only signoff is allowed for integration phases.

- [ ] **Step 3: Run final backend quality commands**

```bash
python scripts/quality_gate.py
pre-commit run --all-files
```

- [ ] **Step 4: Run final frontend quality commands**

```bash
cd frontend && npm run type-check
cd frontend && npm run lint
cd frontend && npm run build
```

- [ ] **Step 5: Run project-required local deployment checks**

```bash
bash scripts/pre-deploy-check.sh
bash scripts/ci-local.sh all
```

- [ ] **Step 6: Run measurable auth and browser verification before the final bundle**

```bash
git grep -n "AuditLog\|log_audit" -- src/core/api/auth/router.py
cd frontend && npm run test:e2e -- auth.spec.ts
```

Expected: every auth audit-log write is visibly wrapped in `best_effort`, and the browser suite covers login, refresh, and logout under the cookie session model.

- [ ] **Step 7: Prepare the final external review bundle**

Bundle must include:

- baseline evidence from Phase 0
- one checkpoint artifact per completed phase
- new test inventory with markers used
- explicit happy path, unhappy path, and user-behavior coverage summary
- residual risks, including any temporary compatibility exceptions
- explicit note that alternate JWT verification paths and any remaining tenant header fallbacks were reviewed for residual risk

- [ ] **Step 8: Update repository documentation and clean up the dedicated worktree**

```bash
git worktree remove .claude/worktrees/release-hardening --force
```

Required documentation updates after implementation signoff:

- `docs/SPRINT-TRACKER.md`
- `AGENTS.md`
- `CLAUDE.md`

---

## Cross-Phase Verification Rules

1. Every implementation task begins with a focused failing test and must show the exact RED failure before the first code edit.
2. After the first substantive edit, rerun the same focused test before any broader validation.
3. New backend test files must use the correct markers, including `@pytest.mark.security` or `@pytest.mark.integration` where applicable.
4. Every phase must include one happy path, one unhappy path, and one user-observable behavior test.
5. Every integration phase must be exercised against the real backend, not only mocked infrastructure.
6. Any new auth-related audit log write must use `async with best_effort(...)` per project rules.

## Decisions

- This is a superpowers execution plan intended for external review, so tasks are checkbox-tracked, commit-sized, and verification-first.
- The file path remains `2026-04-25-pre-existing-issues-cleanup.md`, but this file is now the canonical release-hardening execution plan and supersedes the earlier cleanup framing.
- Auth target is full secure httpOnly cookie migration, not interim localStorage hardening.
- Browser deployment ordering is backend Phase 4 before frontend Phase 5 so cookie-setting behavior exists before browser clients stop reading persisted tokens.
- Query-string tokens are forbidden for normal HTTP flows; any temporary WebSocket exception must be explicitly documented in the checkpoint artifact.
- Production setup/bootstrap must be closed by default and enabled only by explicit setup mode.
- ActivePieces tenant ownership must be derived from first-party mappings, not payload `tenant_id`.
- Unless a future approved design says otherwise, the session model remains stateless JWTs in secure cookies rather than a new DB-backed session table.
- Bootstrap consolidation is deferred to an approved spec and is not implementation work in this plan.
- Vendor source trees remain excluded from scope.
- Supported local dev compose now means `.env.local` plus explicit compose project `sanskritisetuorg`; this is the only validated local runtime contract for continuing this plan.

## Further Considerations

1. If the reviewer wants a smaller first approval set, the safe release-blocking cut line is Phase 1 through Phase 3.
2. If any WebSocket surface cannot move to cookie-based browser auth, record the reason before Phase 6 so it becomes an explicit exception rather than a late discovery.

## Lessons Learned

1. Audit the canonical runtime path first. For this repo the live backend path is `src/main.py -> src/core/api/router_registry.py`; secondary bootstrap surfaces exist and can mislead the fix.
2. Do not let normal HTTP auth depend on FastAPI query binding. If `token` must be rejected on `Request`, force HTTP auth through explicit header/cookie extraction.
3. Setup route registration and public allowlisting must change atomically. Fixing only one side leaves either a broken bootstrap path or a still-public surface.
4. Public runtime code must never mutate live `.env`. Use a reviewed bootstrap artifact and make it single-use.
5. Webhook payload `tenant_id` is diagnostic only. Tenant authority must come from first-party flow or connection bindings.
6. Supported local dev compose entrypoints must all use the same env file and the same explicit compose project. Here that is `.env.local` plus `-p sanskritisetuorg`.
7. Never disable a healthcheck in an override while downstream services still declare `condition: service_healthy`.
8. When Alembic fails on duplicate root tables, inspect `alembic_version` before changing migrations. An empty version table on a populated schema is an environment-state problem, not a schema-definition problem.
9. Local signoff can still be blocked by environment gaps: `pre-commit run --files ...` currently needs `python3.11`, and some integration auth tests skip when the PostgreSQL test DB is not present on ports `5435` or `5455`.
10. Current Playwright auth scaffolding still assumes localStorage-backed browser auth. Do not start Phase 5 without first updating that test scaffolding.

## Next Agent Start Here

1. Treat the current stop point as Phase 5 partial completion. Phases 1 through 4 are fully implemented and validated.
2. Write frontend unit and e2e tests for the cookie-backed session state in Phase 5:
   - `frontend/tests/unit/TokenStorage.test.ts` — assert tokens are NOT persisted in localStorage
   - `frontend/tests/e2e/auth.spec.ts` — assert login, refresh, and logout work under cookie auth
3. Once Phase 5 tests are green, start Phase 6 (WebSocket auth migration) and keep the WebSocket query-token compatibility exception explicitly time-bounded.
4. Continue with Phase 7A through 7E in parallel where possible.
5. Use the live stack commands from Phase 7F if runtime validation is needed again.
6. Backfill the external-review checkpoint bundle for Phases 1 through 5 once Phase 5 is complete.

## Reproduction Commands For The Next Agent

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-dev-secrets.ps1 -Force
docker compose -p sanskritisetuorg --env-file .env.local -f docker-compose.yml -f docker-compose.dev.yml up -d

# Phase 3 validation
python -m pytest tests/integration/test_webhook_security.py -v --stepwise
python -m pytest tests/integration/test_webhook_endpoint_real.py -v --stepwise

# Phase 4 validation
python -m pytest tests/integration/test_auth_cookie_session.py -v --stepwise

# Phase 5 frontend validation
cd frontend
npm run type-check
npm run lint
```
