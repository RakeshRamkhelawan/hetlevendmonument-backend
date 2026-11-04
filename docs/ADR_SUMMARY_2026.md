# Architecture Decision Records (ADR) – SanskritiSetu 2026

**Status**: Active Architecture Decisions
**Date**: January 12, 2026
**Scope**: Collaborative Workflow Builder, Real-Time Sync, Multi-Tenant SaaS

---

## ADR-001: Yjs + WebSocket as Collaboration Core

### Context
A real-time collaborative workflow builder (ReactFlow) requires presence, undo/redo, and high reliability for concurrent editing. CRDTs (Conflict-Free Replicated Data Types) are the standard approach for this use case and have proven implementations (Figma, Notion, Excalidraw).

### Decision
- **Yjs** is used as the CRDT layer: Y.Doc containing Y.Map/Y.Array for nodes, edges, and workflow metadata per workflow
- **y-websocket** (or HocusPocus-equivalent) is the primary transport over WebSockets
- Document state persisted server-side as binary snapshots (Y.Doc.encode()) in PostgreSQL or object storage

### Alternatives
- **Custom diff/patch system**: More control but significantly more complex, error-prone, and lacks community patterns
- **y-webrtc only**: Simpler P2P setup but lacks central control, persistence, and audit capabilities

### Consequences
**Positive:**
- Robust sync semantics with well-documented patterns (Yjs guides, excalidraw patterns)
- Offline tolerance and automatic conflict resolution via CRDT semantics
- Large ecosystem (editor bindings, persistence providers, awareness plugins)

**Negative:**
- Requires separate WebSocket service management and horizontal scaling
- Team must understand CRDT fundamentals for debugging complex scenarios
- Binary format requires versioning strategy for upgrades

---

## ADR-002: WebSocket (wss://) for Canvas Sync, Not WebRTC DataChannels

### Context
The builder requires real-time data synchronization but no audio/video. Both WebSocket and WebRTC DataChannels are technically viable; WebSocket is simpler and more aligned with server-orchestrated sync.

### Decision
- **WebSocket (wss://)** is the standard transport for collaborative workflow data
- WebRTC is reserved for future media features (screen sharing, video); not used for state sync
- All realtime connectivity over **wss://** (TLS 1.3, no ws:// in production)

### Alternatives
- **WebRTC DataChannels**: Peer-to-peer, low latency, but complex signaling/NAT traversal and overkill for pure data sync
- **Polling/SSE**: Simpler but higher latency, one-way, and poor resource efficiency

### Consequences
**Positive:**
- Simpler architecture with server control and audit points
- Better integration with Yjs sync patterns (y-websocket natively supports WebSocket)
- Easier troubleshooting and logging

**Negative:**
- Not ideal for high-bandwidth media later (separate WebRTC solution required then)
- Server must manage WebSocket scaling (connection limits, memory per connection)

---

## ADR-003: Multi-Tenancy via Shared DB + tenant_id + RLS

### Context
Platform must serve multiple independent organizations with strict data isolation. Three patterns exist: per-tenant database, per-tenant schema, or shared schema with tenant_id + optional Row-Level Security.

### Decision
- **Single PostgreSQL cluster**, shared schema across all tenants
- **tenant_id column** on all multi-tenant tables (workflows, users, audit_logs, etc.)
- **Row-Level Security (RLS)** policies enforce tenant isolation at the database level: `USING (tenant_id = current_setting('app.tenant_id'))`
- Tenant context injected via FastAPI dependency → Postgres `SET app.tenant_id = :tenant_id` before each query

### Alternatives
- **Per-tenant database**: Strongest isolation but high operational overhead (backups, migrations, upgrades)
- **Per-tenant schema**: Good isolation but more schema management and replication complexity
- **Shared schema without RLS**: Cheaper but risks data leakage if application layer misconfigured

### Consequences
**Positive:**
- Simplified migrations (single schema version)
- Better resource utilization and cost efficiency
- Easier backups and disaster recovery (single database)
- Simpler tenant onboarding (instant provisioning)

**Negative:**
- Misconfiguration in app or RLS can lead to data leakage; strict testing required
- All tenants share same compute (noisy neighbor problem on high-load tenants)
- Compliance per-tenant audits harder (cross-tenant queries complex)

---

## ADR-004: Tenant Resolution via Subdomain/Header + FastAPI Dependency

### Context
Every request must execute in the correct tenant context. Tenant identity can be conveyed via hostname (subdomain) or request header, then validated and injected centrally.

### Decision
- **Tenant identification** via:
  - Subdomain: `{tenant-slug}.sanskritisetu.org` → DNS/config lookup
  - Header: `X-Tenant-Id` (validated against JWT claim)
  - JWT claim: `tenant_id` or `org_id` from OIDC provider
- **Central FastAPI dependency** `get_current_tenant()` validates and injects `TenantContext` into all handlers
- Dependency enforces: validate JWT → extract tenant → check permission → inject context
- No requests proceed without validated tenant context

### Alternatives
- **Tenant from query/body**: Client-specified, error-prone, easy to miss in some endpoints
- **Global variables or implicit context**: Unsafe, non-testable, breaks in async/concurrent scenarios

### Consequences
**Positive:**
- Consistent tenant resolution across all endpoints (one place to change logic)
- Enforced by framework (FastAPI dependency injection)
- Easy to test with dependency override

**Negative:**
- Requires DNS/host configuration and clear client documentation
- Subdomain approach requires wildcard certificate or SAN setup
- Team must never skip the dependency (code review discipline)

---

## ADR-005: Next.js 14 App Router for SSR/ISR + Client Components for Canvas

### Context
Need good performance (Core Web Vitals), SEO for public pages, and rich interactive builder UX. Next.js 14 App Router supports hybrid rendering: SSR for dynamic content, ISR for static content, and client components for interactivity.

### Decision
- **SSR pages**: Login, dashboard, workflow list (tenant-scoped, user-specific, dynamic)
- **ISR pages**: Help docs, pricing, terms (revalidate every 60s, cached at edge)
- **Client components** (use "use client"): Workflow canvas, AI-assist panel, activity feed
- **Code splitting**: ReactFlow and Yjs imported only on builder page entry; AI panel lazy-loaded on first open

### Alternatives
- **Pure SPA (client-side render)**: Simpler initially but poor FCP, poor SEO, high JS bundle
- **All SSR**: Complex for interactive components; forces server-side WebSocket handling (doesn't scale)
- **MPA (separate Next.js for pages, SPA for builder)**: Duplicate tooling, complex handoffs

### Consequences
**Positive:**
- LCP < 2.5s achievable (no blank screen on network=slow)
- Good SEO for public pages (indexable, fast metadata)
- Combines SEO best practices with rich UX
- Edge-optimized ISR for static assets (Vercel/Netlify deployment)

**Negative:**
- More complex build pipeline and route configuration
- Requires careful bundling (missing one dynamic import = huge bundle)
- Team must understand SSR/CSR trade-offs and when to use each

---

## ADR-006: AI-Assist as Concept/Draft Layer with LangGraph Orchestration

### Context
AI will provide workflow suggestions and mutations (optimize, auto-fix, decompose). Safety and explainability are critical. LangGraph is suited for stateful AI orchestration with clear node/edge semantics.

### Decision
- **AI output always starts as "draft" or "concept"** workflow/mutation (not directly applied to published workflow)
- **LangGraph** runs as separate service/module with explicit state graphs (analyze → generate → validate → ready-for-review)
- **FastAPI exposes** `/api/v1/ai/plan-workflow` with clear contract: takes prompt + workflow state → returns suggested_changes + reasoning
- **User explicitly applies** suggestions via "Accept" button; merge action logged as "User applied AI suggestion", not "AI modified workflow"

### Alternatives
- **AI directly modifies live workflows**: Faster UX but risks unintended changes, audit trail gaps, and compliance issues
- **No central orchestration** (LLM calls scattered across endpoints): Inconsistent behavior, harder to govern and audit
- **Fully autonomous agents** (no human review): Maximum efficiency but maximum risk

### Consequences
**Positive:**
- Clear human-in-the-loop governance (AI assists, humans decide)
- Full audit trail (who applied which AI suggestion)
- Easier to explain AI decisions (reasoning field logged)
- Compliant with GDPR/SOC2 (AI actions traceable and reversible)

**Negative:**
- Extra UX step (review before apply) slows workflow
- Separate LangGraph service adds operational complexity
- Requires clear RLS/whitelist for AI tools (can't auto-escalate permissions)

---

## ADR-007: Standardized Audit Logging with Async RabbitMQ Pipeline

### Context
Compliance (GDPR, SOC2) requires complete audit trails for sensitive actions (workflow changes, executions, AI suggestions, user role changes). Synchronous logging can slow requests; async decouples performance from logging overhead.

### Decision
- **Audit log schema** (immutable, never updated):
  - `tenant_id`: Multi-tenant scope
  - `actor_id`, `actor_type`: Who (user/service/system)
  - `resource_type`, `resource_id`: What (workflow/node/edge)
  - `action`: Create/Update/Delete/Execute
  - `before`, `after`: JSON snapshots for before-after comparison
  - `timestamp`, `correlation_id`: Timing and link related actions
  - `ip_address`, `user_agent`: Context
- **Async pipeline**: On sensitive action, emit event to RabbitMQ queue → consumer service validates + stores in audit_logs table
- **Retention**: 90 days (configurable per compliance mandate)
- **Indexing**: Full-text search on actor, resource, action for compliance queries

### Alternatives
- **Ad-hoc logging** (free-text): Inconsistent, hard to search, unreliable
- **Synchronous audit** (request-blocking): Simple but adds latency to every operation
- **Event sourcing everywhere**: Full immutability but architectural overkill for audit alone

### Consequences
**Positive:**
- Consistent, searchable audit data (compliance audits easier)
- No performance penalty on application requests
- Decoupled: audit service can fail without blocking user actions
- Clear compliance trail (actor/action/before-after traceable)

**Negative:**
- Additional infrastructure (RabbitMQ consumer, audit-log table, indices)
- Eventual consistency (audit log lags slightly behind action)
- Requires monitoring of queue depth and consumer lag

---

## ADR-008: Forbidden Patterns – y-webrtc Standalone, Custom CRDT, In-Memory Yjs

### Context
Two tempting shortcuts exist: using y-webrtc alone for simplicity, or building a custom diff/patch system for more control. Both introduce unacceptable risk in a production SaaS.

### Decision
- **y-webrtc is forbidden** for critical production workflows (only allowed for demos, sandboxes, offline-first prototypes with server-side sync as fallback)
- **Custom CRDT/diff mechanisms are forbidden**; Yjs is the exclusive CRDT library
- **In-memory Yjs without persistence is forbidden**; every Y.Doc must be persisted to server storage (DB/object storage)

### Alternatives
- **y-webrtc as sole transport**: Lower infra cost initially but unacceptable risks (single-peer failure → data loss, no audit, NAT traversal issues)
- **Custom CRDT**: Full control but 10x the complexity, unmaintainable, incompatible with reactive frameworks

### Consequences
**Positive:**
- Reduced architectural complexity (one standard: Yjs + y-websocket)
- Leverage mature, battle-tested tooling (Figma, Notion use Yjs)
- No custom diff logic to debug or maintain
- Deterministic conflict resolution via CRDT (not manual)

**Negative:**
- Yjs ecosystem lock-in (limited escape routes)
- Operational dependency on y-websocket/HocusPocus providers
- Team must invest in understanding CRDT fundamentals

---

## ADR-009: Outline View (Accessibility + Keyboard Navigation)

### Context
Complex interactive canvas UIs often exclude screenreader users, keyboard-only users, and mobile/touch users. WCAG 2.1 AA requires multiple modalities of interaction.

### Decision
- **Separate "Outline" or "Structure" panel** alongside canvas showing hierarchical node list
- **Keyboard navigation**: Arrow keys to navigate, Enter to focus on canvas, Space to edit
- **Accessibility features**:
  - ARIA roles/labels for outline items and canvas
  - Announcers for canvas changes ("Node added", "Edge deleted", "Workflow saved")
  - Focus management after AI mutations (focus outline item, announce change)
- **Mobile**: Outline is primary on mobile (simplified canvas, tap to expand detail panel)
- **Sync with Yjs**: Outline updated automatically when nodes/edges change (Y.Map.observe callback)

### Alternatives
- **Canvas-only**: Simpler UX but excludes accessibility users, poor keyboard navigation
- **Separate page for outline**: Better organization but harder to cross-reference with visual canvas

### Consequences
**Positive:**
- WCAG 2.1 AA compliant (passes axe-core scan)
- Keyboard users and screenreader users can operate builder
- Mobile UX improved (outline + detail panels vs. tiny canvas)
- Non-visual debugging aided (text representation of flow)

**Negative:**
- Extra UI components (outline panel, sync logic)
- Team must implement and test a11y patterns
- Design must balance two representations (canvas + outline)

---

## ADR-010: Separate Yjs Sync-Server (Not Embedded in Next.js or FastAPI)

### Context
WebSocket state is persistent (user is connected for 30+ min). Next.js is stateless (edge/serverless functions); FastAPI can handle it but couples business logic with realtime sync logic.

### Decision
- **Dedicated Yjs sync-server** (y-websocket or HocusPocus) running on separate port (e.g., 8001)
- **Isolation**: Next.js handles HTTP (SSR, API routes, auth), FastAPI handles REST CRUD, Yjs-server handles wss:// realtime
- **Scaling**: Yjs-server instances behind load balancer; Redis pub/sub for cross-instance fanout
- **Deployment**: Containerize as separate service in docker-compose; separate Kubernetes Deployment in production

### Alternatives
- **Embed WebSocket in Next.js API routes**: Doesn't work (stateless, FaaS incompatible)
- **Embed WebSocket in FastAPI alongside REST**: Works locally but couples concerns, harder to scale independently

### Consequences
**Positive:**
- Clean separation of concerns (HTTP vs WebSocket)
- Independent scaling (scale Yjs-server under high realtime load without affecting API)
- Easier to debug (separate logs, separate monitoring)
- Standard pattern (follows many SaaS platforms)

**Negative:**
- Extra service to deploy and monitor
- Cross-service communication requires care (Redis pub/sub, topic management)
- More containers/processes to manage locally

---

## ADR-011: JWT with Explicit Tenant/Role Claims, No Custom Token Format

### Context
Authentication and authorization are critical security boundaries. Custom token formats and ad-hoc auth checking are common vectors for breaches.

### Decision
- **JWT (RFC 7519)** is the only token format; claims must include:
  - `tenant_id` or `org_id`
  - `sub` (user ID)
  - `email`
  - `roles` (array of role strings: ["admin", "editor", "viewer"])
  - `permissions` (optional fine-grained perms)
  - `aud` (audience = API endpoint URL)
- **No custom crypto or ad-hoc encoding**; use standard JWT library (PyJWT for Python, jsonwebtoken for Node.js)
- **Scopes for delegated access**: `workflow:read`, `workflow:write`, `workflow:execute`, `admin:full`
- **Token lifetime**: 15min access token, 7-day refresh token; validate on every endpoint

### Alternatives
- **Custom token format**: Full control but incompatible with standard tools, audit, and debugging
- **Session cookies only**: Simpler but doesn't work for mobile/SPA, no explicit scopes

### Consequences
**Positive:**
- Standard format compatible with all tools/libraries
- Explicit tenant/role claims prevent authorization bypasses
- Easy to audit (decode token → see claims)
- Interoperable with OIDC providers (Google, Azure, etc.)

**Negative:**
- Token revocation requires additional logic (blacklist table, TTL)
- Developers must understand JWT semantics to avoid common pitfalls (clock skew, algorithm confusion)

---

## ADR-012: No Unauthenticated WebSocket Access; Always Validate Tenant

### Context
WebSockets are long-lived connections. Forgetting to validate authentication/authorization can expose workflows to unauthorized access.

### Decision
- **Every WebSocket upgrade request** must:
  1. Extract JWT from headers/URL parameter
  2. Validate JWT signature and expiration
  3. Extract tenant_id from JWT
  4. Validate tenant_id matches requested workflow's tenant_id
  5. Check user has WORKFLOW_READ (or WORKFLOW_EXECUTE) permission
- **Reject connection** if any validation fails (close socket immediately)
- **Middleware pattern**: Centralized `validateWebSocketAuth()` called before accepting upgrade

### Alternatives
- **Validate after connection**: Simpler but risk of brief unauthorized access
- **No auth on WebSocket, rely on opaque session ID**: Fragile, hard to audit

### Consequences
**Positive:**
- No unauthorized access to workflows via WebSocket
- Clear audit trail (rejected connections logged)
- Enforces security at the transport layer, not business logic

**Negative:**
- Slightly higher latency on connection (JWT validation)
- Client must always include valid JWT in WebSocket handshake

---

## ADR-013: AI Tool Whitelist + Max Impact Per Tenant

### Context
AI agents making unbounded tool calls risk escalating privileges, modifying out-of-scope resources, or triggering unintended actions.

### Decision
- **AIToolPolicy** table per tenant:
  ```python
  tenant_id | tool_name | allowed_actions | max_impact | requires_approval
  1 | workflow_optimizer | [read, suggest] | draft_only | false
  1 | node_suggester | [read, suggest] | draft_only | false
  2 | workflow_optimizer | [read, suggest] | owned_only | true
  ```
- **LangGraph validates** before invoking any tool:
  - Check policy entry exists
  - Check action is in allowed_actions
  - Enforce max_impact (draft_only = never write to published; owned_only = only own tenant)
  - If requires_approval=true, emit event for human review before executing

### Alternatives
- **Unbounded tool access**: Faster but dangerous (AI can delete workflows, escalate roles, etc.)
- **Per-tool hardcoded checks**: Works but scattered logic, hard to manage per-tenant

### Consequences
**Positive:**
- Clear, auditable AI boundaries per tenant
- Prevents privilege escalation via AI
- Easy to restrict AI on high-security tenants
- Compliant with GDPR/SOC2 (policy audit trail)

**Negative:**
- Extra database table and policy validation logic
- Team must define policies per tenant (or sensible defaults)

---

## ADR-014: No Direct AI Mutations to Live Workflows; Draft-First Always

### Context
AI suggesting changes is good; AI silently modifying published workflows is dangerous.

### Decision
- **AI changes always start as "draft" status**:
  - Create new workflow variant with `status: draft`
  - Store in `workflow_drafts` or as separate `workflow_version`
  - Link to original published workflow
- **UI shows side-by-side comparison**: Original (published) vs. AI suggestion (draft)
- **On user approval**: Merge draft → published version, log action as "User applied AI suggestion"
- **AI never has permission** to directly update published workflows (permission model enforces this)

### Alternatives
- **AI directly modifies published**: Immediate effect but risky and hard to undo
- **AI in separate sandbox**: Complex and disconnected from user's actual workflows

### Consequences
**Positive:**
- Clear audit trail (who approved, what changed)
- Easy to rollback (original still exists as published)
- Safer for high-stakes workflows (no accidental changes)
- Compliant with GDPR (AI actions attributed to user who approved)

**Negative:**
- Extra UX step (review + approve)
- Database versioning complexity (draft vs published)

---

## ADR-015: Horizontal Scaling of Yjs-Server via Redis Pub/Sub

### Context
Single Yjs-server instance will become a bottleneck. Multiple instances need to coordinate document updates.

### Decision
- **Redis pub/sub** for cross-server event fanout:
  - Server A receives document mutation → publishes to `yjs:workflow:{workflowId}` channel
  - Servers B, C listening to same channel → broadcast to their connected clients
- **Sticky sessions** (by workflowId or sessionId hash) to avoid unnecessary cross-server syncs (if user's server has doc in memory, future mutations go to same server)
- **Yjs persistence** ensures state is recoverable even if all Yjs-servers crash (restored from S3 snapshots + incremental updates)

### Alternatives
- **Single Yjs-server**: Simpler but non-HA, hard failure = all users disconnected
- **Each server separate**: No cross-server updates, users can't sync
- **Kubernetes StatefulSet with persistent volumes**: More complex, higher latency

### Consequences
**Positive:**
- Horizontal scaling (add more Yjs-servers as load grows)
- No single point of failure
- Familiar pattern (Redis pub/sub well-understood)

**Negative:**
- Redis dependency (another service to manage)
- Network latency between Yjs-servers (slight delay on document propagation)
- Sticky session complexity (load balancer configuration)

---

## ADR-016: RBAC Model with Explicit Roles + Permissions

### Context
Multi-tenant application requires role-based access control (RBAC) for workflows, admin functions, audit logs, and sensitive operations. FastAPI's dependency injection system is well-suited for declarative RBAC patterns.

### Decision
- **Explicit roles** (e.g., `tenant_admin`, `workflow_editor`, `workflow_viewer`, `audit_viewer`, `billing_admin`)
- **Explicit permissions** modeled as `(resource, action)` tuples:
  - Workflow: `workflow.create`, `workflow.read`, `workflow.update`, `workflow.delete`, `workflow.execute`, `workflow.share`
  - Audit: `audit.read`
  - Admin: `tenant.manage`, `user.manage`, `billing.manage`
- **Database model**: User → Role (many-to-many) → Permission (many-to-many)
  ```python
  class Role(Base):
      id: int
      tenant_id: int
      name: str  # "editor", "viewer", "admin"
      permissions: list[Permission]  # ORM relationship

  class UserRole(Base):
      user_id: str
      role_id: int
      tenant_id: int
  ```
- **FastAPI dependencies** enforce RBAC via `Depends()`:
  ```python
  async def require_permission(
      required_permission: str,
      current_user: User = Depends(get_current_user),
      db: AsyncSession = Depends(get_db_session),
  ) -> User:
      user_perms = await fetch_user_permissions(current_user.id, db)
      if required_permission not in user_perms:
          raise HTTPException(status_code=403, detail="Forbidden")
      return current_user

  @app.post("/workflows")
  async def create_workflow(
      db: AsyncSession = Depends(get_db_session),
      current_user: User = Depends(require_permission("workflow.create")),
  ):
      # Only users with workflow.create permission reach here
  ```

### Alternatives
- **Hardcoded role checks in routes** (`if current_user.role == "admin"`): Fast initially but unmaintainable, no granular control, difficult to audit
- **External AuthZ service** (Auth0 FGA, Open Policy Agent): Highly flexible but operational overhead for first phase; can be added later as complexity grows

### Consequences
**Positive:**
- Clear, auditable permission model (database of truth)
- Easy to grant/revoke permissions per user or role
- Simple to extend to ABAC/ReBAC patterns later (add conditions/attributes)
- Compliance-friendly (explicit permissions logged)

**Negative:**
- Database schema and migration complexity (roles, permissions, user_roles tables)
- Role/permission management requires admin UI (onboarding/operational overhead)
- Runtime permission checks add slight latency (mitigate with caching)

---

## ADR-017: Keyboard-First Navigation + Focus Management for Builder

### Context
Workflow builder is complex interactive UI with many elements. WCAG 2.1 AA requires full keyboard navigation, clear focus states, and screenreader announcements. Keyboard-first design benefits all users (power users, accessibility users, high-latency environments).

### Decision
- **Full keyboard support** for builder interactions:
  - **Tab/Shift+Tab**: Navigate between nodes, outline items, panels, toolbar
  - **Arrow keys**: Move selected node (Up/Down/Left/Right in direction of canvas)
  - **Enter/Space**: Open node config panel, expand outline item
  - **Delete/Backspace**: Delete selected node/edge
  - **Ctrl+Z/Cmd+Z**: Undo (from Yjs)
  - **Ctrl+Y/Cmd+Shift+Z**: Redo
  - **Escape**: Close panels, deselect
  - **?**: Show keyboard shortcuts overlay
- **Focus management**:
  - Visible focus ring (outline, highlight, or visual indicator) on all interactive elements
  - Logical tab order: canvas → outline panel → details panel → toolbar → help
  - Focus moves to newly created node (so keyboard user can immediately edit it)
  - Focus announced via screenreader (via `aria-live` region)
- **Interaction feedback**:
  - Screenreader announces: "Node A added", "Node moved left", "Edge deleted"
  - Visual feedback: highlight, animation, or color change on focus

### Alternatives
- **Mouse/touch only**: Not WCAG 2.1 AA compliant, excludes keyboard-only and power users
- **Minimal keyboard support** (Tab between buttons only): Better than nothing but inadequate for builder; complex workflows require efficient navigation

### Consequences
**Positive:**
- WCAG 2.1 AA compliant (full keyboard navigation)
- Better UX for power users (faster navigation with shortcuts)
- More inclusive (users with motor disabilities, high-latency networks, accessibility tools)
- Easier testing and debugging (keyboard-only testers catch issues early)

**Negative:**
- Higher UX/design complexity (multiple interaction modalities to consider)
- More testing burden (axe-core, screenreader tests, keyboard path tests)
- Keyboard shortcut conflicts possible (browser, OS, assistive tech)
- Ongoing maintenance as new features added

---

## ADR-018: Security Layered Architecture in FastAPI (Authn/Authz/Validation)

### Context
Backend must be production-grade secure: validate authentication, enforce authorization, sanitize input, rate-limit, and audit. FastAPI's middleware and dependency systems support a clean, layered approach.

### Decision
- **Layer 1: Authentication (Middleware)**
  - Validate JWT signature, expiration, audience
  - Extract user_id, tenant_id, roles from JWT claims
  - Reject invalid tokens (401 Unauthorized)

- **Layer 2: Tenant Binding (Dependency)**
  - Confirm JWT tenant_id matches request tenant (from subdomain/header)
  - Inject TenantContext into request scope
  - All queries automatically scoped to tenant

- **Layer 3: Authorization (Dependency)**
  - Check RBAC: user must have required permission for resource+action
  - Reject insufficient permissions (403 Forbidden)

- **Layer 4: Input Validation**
  - FastAPI Pydantic models validate request body (type, range, length, regex)
  - SQL injection prevented by parameterized queries (SQLAlchemy)
  - XXE/CSRF mitigated by framework defaults

- **Layer 5: Business Logic (Service)**
  - Service layer enforces invariants (e.g., "workflow must have exactly one start node")
  - Idempotency checks (prevent duplicate-execute on retry)

- **Layer 6: Audit Logging**
  - Log all sensitive actions (async via RabbitMQ)
  - Before/after snapshots captured

### Alternatives
- **Ad-hoc security in each route**: Security scattered, easy to miss, inconsistent
- **Single catch-all authorization layer**: Less granular, hard to debug specific failures

### Consequences
**Positive:**
- Clear separation of concerns (each layer has one job)
- Security policy centralized (easier to audit and enforce)
- Easier to test each layer independently
- Scalable (add new constraints at appropriate layer, not scattered)

**Negative:**
- Strict discipline required (team must respect layer boundaries)
- Documentation essential (onboarding cost)
- Performance overhead (multiple checks); mitigate with caching/optimization

---

## ADR-019: A11y as Non-Functional Requirement (From Day One)

### Context
Complex interactive tools (canvas, editors) often get accessibility bolted on later, requiring expensive refactors. Early a11y integration is more cost-effective and produces better outcomes.

### Decision
- **A11y is a first-class requirement**, not a retrofit:
  - Every feature has WCAG 2.1 AA acceptance criteria (contrast, keyboard, focus, screenreader)
  - axe-core automated scans in CI pipeline (fail if issues found)
  - Manual screenreader testing (NVDA, JAWS, VoiceOver) for critical workflows (login, builder, dashboard)
  - Accessibility code review in PR process (reviewer checks keyboard paths, ARIA labels, announcements)

- **Testing tools integrated**:
  - axe-core (auto-scan) in Vitest
  - Playwright with screenreader simulation (basic)
  - Manual screenreader sessions (monthly, critical UX)

- **Developer guidance**:
  - A11y checklist added to component development template
  - Accessibility patterns documented (focus management, announcers, outline view)
  - Design system includes accessible component variants (high contrast, larger touch targets)

### Alternatives
- **A11y as post-launch hardening phase**: Leads to expensive rework of layouts, semantics, scripts
- **Automatic checks only**: Catches ~30% of issues; misses UX-level and contextual problems
- **Manual a11y testing only**: Too slow for iteration; better combined with automation

### Consequences
**Positive:**
- Lower long-term cost (catch issues early vs. rework later)
- Better UX for all users (accessible design is often simpler, clearer)
- Fewer last-minute compliance surprises
- Easier to attract/retain talent (inclusive culture)

**Negative:**
- Slightly higher initial development time per component
- Team needs a11y training/guidance (investment in knowledge)
- Screenreader testing is slow (requires real devices/VMs, not fast in CI)
- Some browser/assistive-tech combinations hard to test (coverage gaps remain)

---

## ADR-020: A11y Outline View as Primary Navigation Path (Not Canvas-Only)

### Context
Visual canvas-based builders can exclude screenreader users and make keyboard-heavy workflows tedious. A parallel outline/tree view provides equal access and faster navigation for keyboard users.

### Decision
- **Outline view** (text-based, hierarchical list or tree) is equally maintained as canvas:
  - Lists all nodes in hierarchical order (with parent-child relationships, groups)
  - Updates in real-time when canvas changes (via Yjs observer)
  - Fully keyboard-navigable (arrow keys, Enter to edit, Delete to remove)
  - ARIA roles: `role="tree"` with `role="treeitem"` for each node
  - Announcements: "Node added at position 3", "Node moved under group X", "Node deleted"

- **Mobile layout**: Outline is primary on mobile (canvas secondary); tap node to expand detail panel

- **Feature parity**: Outline and canvas are NOT separate modes; both always visible and in-sync
  ```typescript
  // E.g., Outline and Canvas side-by-side on desktop, stacked on mobile
  <div className="workflow-builder">
      <div className="outline-panel">
          <OutlineTree nodes={nodes} onSelect={focusOnCanvas} />
      </div>
      <div className="canvas-panel">
          <ReactFlow nodes={nodes} edges={edges} ... />
      </div>
  </div>
  ```

### Alternatives
- **Canvas-only UI**: Simpler UX for visual users but excludes accessibility users; WCAG violations
- **Separate "view as text" export**: Less maintenance but not live; not a substitute for dual representation

### Consequences
**Positive:**
- WCAG 2.1 AA compliant (alternative non-visual representation)
- Benefits keyboard users (faster navigation with outline)
- Better for mobile UX (outline easier to tap than tiny canvas nodes)
- Easier to understand workflow structure (text + visual)

**Negative:**
- Extra UI real estate (outline panel)
- Sync logic complexity (outline and canvas must stay in perfect sync)
- Design burden (balance two representations)
- Performance on large workflows (1000+ nodes) requires optimization (virtual scrolling in outline)

---

## Summary Table

| ADR     | Title                                           | Status   | Owner              |
|---------|-------------------------------------------------|----------|--------------------|
| ADR-001 | Yjs + WebSocket as Collaboration Core           | ✅ Active | Architecture       |
| ADR-002 | WebSocket (wss://) for Canvas Sync              | ✅ Active | Architecture       |
| ADR-003 | Multi-Tenancy via Shared DB + RLS               | ✅ Active | Backend            |
| ADR-004 | Tenant Resolution via Subdomain/Header          | ✅ Active | Backend            |
| ADR-005 | Next.js 14 SSR/ISR + Client Components          | ✅ Active | Frontend           |
| ADR-006 | AI-Assist as Draft Layer                        | ✅ Active | AI/Architecture    |
| ADR-007 | Standardized Audit Logging + Async              | ✅ Active | Backend/Compliance |
| ADR-008 | Forbidden: y-webrtc, Custom CRDT, In-Memory Yjs | ✅ Active | Architecture       |
| ADR-009 | Outline View + Accessibility                    | ✅ Active | Frontend           |
| ADR-010 | Separate Yjs Sync-Server                        | ✅ Active | Architecture       |
| ADR-011 | JWT with Tenant/Role Claims                     | ✅ Active | Security           |
| ADR-012 | No Unauthenticated WebSocket                    | ✅ Active | Security           |
| ADR-013 | AI Tool Whitelist + Max Impact                  | ✅ Active | AI/Security        |
| ADR-014 | Draft-First AI Mutations                        | ✅ Active | AI/UX              |
| ADR-015 | Horizontal Scaling via Redis Pub/Sub            | ✅ Active | Infra              |
| ADR-016 | RBAC Model with Explicit Roles + Permissions    | ✅ Active | Backend/Security   |
| ADR-017 | Keyboard-First Navigation + Focus Management    | ✅ Active | Frontend/A11y      |
| ADR-018 | Security Layered Architecture in FastAPI        | ✅ Active | Backend/Security   |
| ADR-019 | A11y as Non-Functional Requirement (Day One)    | ✅ Active | Frontend/Product   |
| ADR-020 | A11y Outline View as Primary Navigation         | ✅ Active | Frontend/A11y      |
| ADR-021 | Agent Lifecycle System (ALS) Framework          | ✅ Active | AI/Architecture    |
| ADR-022 | Learning Mixin + @auto_learn Pattern            | ✅ Active | AI/Learning        |
| ADR-023 | Agent Router + Health Monitor Architecture      | ✅ Active | AI/Architecture    |
| ADR-024 | Conversation Voice Agent (CVA) Design           | ✅ Active | AI/Voice           |
| ADR-025 | Digital Twin with OODA-Loop                     | ✅ Active | AI/Digital Twin    |
| ADR-026 | Hybrid Search (BM25 + Vector)                   | ✅ Active | Search/AI          |
| ADR-027 | Agent Council Governance Framework                | ✅ Active | AI/Governance      |
| ADR-028 | Proactive Monitor Framework                       | ✅ Active | AI/Governance      |
| ADR-029 | Egress Control + Alert Notification Bridge        | ✅ Active | Security/Ops       |
| ADR-030 | RLS Hardening + Stale Cleanup                     | ✅ Active | Security/DB        |
| ADR-031 | Platform-wide AI Act 2026 Governance and Wiring   | ✅ Accepted | Compliance/AI    |

> **Note**: ADR-021 through ADR-031 are maintained as individual documents in
> `docs/adr/`. This summary table reflects the current state as of the last update.

---

**Last Updated**: May 26, 2026
**Next Review**: June 2026 (post-launch retrospective)
**Maintained By**: Architecture Team

---

## How to Use This Document

1. **For implementation**: Reference the relevant ADR for technical guidance (context, decision, consequences)
2. **For review**: Check ADR before proposing changes to core patterns
3. **For onboarding**: New team members read relevant ADRs to understand "why" behind decisions
4. **For disputes**: If architecture direction is unclear, refer to the corresponding ADR
5. **To propose changes**: Document as new ADR with alternatives and consequences; seek consensus before implementing
