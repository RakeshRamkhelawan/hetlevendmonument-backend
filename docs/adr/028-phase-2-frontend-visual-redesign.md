# ADR-028: Phase 2 Frontend Scope, Visual Redesign & Brainstorm Alignment

## Status

Accepted -- 2026-05-26

## Context

SanskritiSetu, the Enterprise AI Agent Operating System, is transitioning from its Phase 1 frontend to a comprehensive system in Phase 2. While the backend has matured with advanced enterprise capabilities (Prana Economy, A2A Contracts, ShadowCEO, Digital Twin, Trace Engine, Company-as-Code, YJS Sync, External Agents), the frontend must provide the interfaces to make these "Operating System" features accessible, collaborative, and auditable.

To achieve complete parity between the mature backend architecture and the user-facing interface, the frontend must support **9 priority areas**:

1. **Agent Management** (Dashboard, agent cards, health monitoring, rolling-window failure metrics)
2. **Compliance & Audit** (Consent, audit trail with SHA-256 hash chains, council decisions, right-to-explanation endpoints)
3. **RAG & Knowledge** (Document search, vector quality monitoring, context injection, BM25 Hybrid search configuration)
4. **Integration & Tool Broker** (Tool registry, HITL queue with collaborative steering inputs, approvals)
5. **Enterprise OS Governance** (Prana Economy token ledger, A2A Smart Contracts state transitions, ShadowCEO Adversarial Monitoring)
6. **Cognitive & Execution Observability** (Digital Twin profile, OODA struggle analysis, Trace Engine/Debugger with temporal branching)
7. **Enterprise Company & Org Structure** (Company-as-Code hierarchy, department & role builders, board decision pipelines)
8. **Real-time Collaboration Canvas** (YJS synchronization server, canvas comments, node tagging, live collaborative editing)
9. **External Agent Heartbeat Tracker** (Heartbeat connection directory, status logs, liveness monitoring)

In May 2026, a series of design brainstorm prototypes and HTML/CSS mockups (stored in `.superpowers/brainstorm/`) established the exact visual guidelines, layout architecture, and user experience paradigms for the platform. Sprints 1, 2, and 3 must be retrofitted, and all future sprints built, to conform to these specific brainstorm prototypes.

## Decision

We adopt the **Phase 2 Visual Redesign, Design System, and Brainstorm Prototypes** as the foundation for the frontend development using React, Tailwind CSS, and specific canvas libraries. The implementation follows these technical, layout, and visual decisions:

1. **Layout & UX Architecture (The 3-Panel Studio)**:
   - **Unified Studio Layout**: In accordance with `173-1774947808/full-design-mockup.html` and `design-section-1-architecture.html`, all workflows, templates, and execution builders are consolidated into a single route `/studio`.
   - **Zero-Navigation Workspace**: A fixed 3-panel layout where the **Left Panel** (Library & templates toggle, 220px wide), **Center Panel** (Interactive XYFlow canvas, flex-1), and **Right Panel** (AI Chat Assistent, 280px wide) are visible simultaneously.
   - **Progressive Collapse**: Both the Left and Right panels are fully collapsible to allow power users to expand the canvas to 100% width. On screens smaller than 1200px, the Left Panel automatically collapses into an icon-only sidebar.
   - **No Modals for Node Editing**: In line with the user research (`user-research-findings.html`), node configuration and inspector details are rendered inline in slide-over panels (Left/Right) without blocking or covering the main center canvas.

2. **Visual Fidelity & Theming**:
   - **Vibrant Dark Mode**: Base background is set to a curated dark palette (`#020817` base) combined with harmonious gradients transitioning to royal violet (`#7c3aed`) for primary interactive actions and brand elements.
   - **Intent-Based Search & Node Chips**: Linkerpaneel templates and node selection filters must support searching by user intent (e.g. "Send Slack message" resolves to the specific Slack tool node). Newly spawned nodes display as colorful, high-fidelity tag chips with icons (e.g. Schedule Trigger 📅, AI Analysis 🧠, Slack Notification 💬) as detailed in `design-proposal-card.html`.

3. **Technical Stack & Libraries**:
   - **State Management**: **Zustand** with strict store isolation (e.g., `useAgenticDashboardStore.ts`, `useCompanyStore.ts`, `useAgentStore.ts`).
   - **Data Fetching**: **TanStack Query (React Query)** for caching, automatic invalidation, and server synchronization.
   - **UI Primitives**: **Radix UI** for foundational WCAG AAA accessibility compliance.
   - **Visualizations & Canvas**: **Recharts** (Performance/Prana metrics) and **XYFlow** (Interactive Org Charts, A2A Contract lifecycles, real-time collaboration canvas, and workflow mapping).
   - **Real-time Sync**: **YJS** client-side websocket provider for real-time document and canvas state synchronization.

4. **Full-Spectrum Feature Parity & Proposal Semantics**:
   - **Detailed Proposal Cards**: When the AI proposes changes, proposals must render as detailed cards displaying a summary of actions, list of proposed node chips, and clear Accept/Decline action buttons as defined in `960-1774276292/design-proposal-card.html`.
   - **Enterprise Economy & Smart Contracts**: A visual **Prana & A2A Ledger Explorer** showing live contract state transitions (Proposed -> Agreed -> Executing -> Settled) and Prana token escrows.
   - **Org Chart & Department Builder**: Drag-and-drop hierarchy visualizer linking departments directly to their Prana budgets and automatically activating matching **Domain Packs**.
   - **External Agent Heartbeat Tracker**: A registry listing all connected external agent integrations and displaying their live heartbeat status (flagging missed heartbeats as `INACTIVE`).
   - **Digital Twin Mirror & Consent Dashboard**: A dedicated interface showing the Twin's learned behavioral maps (OODA), OODA struggle analysis, and Art. 7 GDPR consent configuration (4 boolean categories).
   - **Steerable HITL & Temporal Debugger**: Extending the `ApprovalQueue` to allow text/JSON counter-proposals, and the `ReasoningLog` to support **Temporal Time-Machine branching** (stepping back to a reasoning node, changing parameters, and spawning a new path).

5. **Observability & Traceability**:
   - **Mandatory Correlation IDs**: Every request attaches a unique `trace_id` for backend audit cross-referencing.

6. **AI-Aware UI Constraints**:
   - **Token Budget Monitoring**: Real-time token estimation in the UI to prevent blind LLM context window overflows.

7. **Security & Granular Access Control**:
   - **Scope-based RBAC**: Moving from Tier-based to Scope-based access (via JWT) using a `PermissionGate` component.
   - **Frontend PII Masking**: Respecting `data_classification` via `ClassificationWrapper` (blurring/masking sensitive data based on role).

8. **Dynamic Styling & Real-time Integrity**:
   - **CSS Variable Injection**: Multi-tenant white-labeling via runtime variable injection in the `:root`.
   - **Sequence-based WebSockets**: Mandatory sequence number checking in `useAgenticWebSocket` to trigger rehydration on data gaps, with a 2000ms throttle to prevent infinite loops.

## Implementatiestatus (SP-FE-2C t/m SP-FE-2G + ADR-028 afsluiting, 2026-06-28 / 2026-07-01)

De Phase 2 Visual Redesign is in 5 opeenvolgende sprints volledig uitgerold, met ADR-028 afsluiting op 2026-07-01 (CollaborationCanvas dark-mode retrofit -- 9/9 DONE). Alle pagina's en componenten hieronder zijn geimplementeerd, getest (0 failures), en hebben goedgekeurde feature-specs.

### Geimplementeerde pagina's

| Sprint   | Route                      | Component                   | Feature-ID | ADR         |
| -------- | -------------------------- | --------------------------- | ---------- | ----------- |
| SP-FE-2C | `/council`                 | `CouncilDashboard`          | FE-PGS-015 | ADR-019     |
| SP-FE-2C | `/compliance` (retrofit)   | `AuditLogs` dark-mode       | FE-PGS-016 | ADR-028     |
| SP-FE-2D | `/kennis`                  | `Knowledge` full page       | FE-PGS-019 | ADR-028     |
| SP-FE-2D | `/kennis` (audit)          | Integrations ADR-028 audit  | FE-PGS-020 | ADR-028     |
| SP-FE-2E | `/tools`                   | `ToolBrokerRegistry`        | FE-PGS-021 | ADR-015     |
| SP-FE-2E | `/hitl`                    | `HITLQueue` (redesign swap) | FE-PGS-022 | ADR-015     |
| SP-FE-2E | `/tool-audit-logs`         | `ToolAuditLogs`             | FE-PGS-023 | ADR-015     |
| SP-FE-2F | `/prana`                   | `PranaDashboard`            | FE-PGS-024 | ADR-021     |
| SP-FE-2F | `/prana/contracts`         | `A2AContracts`              | FE-PGS-025 | ADR-020     |
| SP-FE-2F | `/shadow-ceo`              | `ShadowCEOMonitor`          | FE-PGS-026 | ADR-016     |
| SP-FE-2G | `/digital-twin` (retrofit) | `DigitalTwin` dark-mode     | FE-PGS-027 | ADR-025/026 |
| SP-FE-2G | `/digital-twin`            | consent gate + OODA         | FE-PGS-028 | ADR-026     |
| SP-FE-2G | `/traces`                  | `TraceViewerPage` swap      | FE-PGS-029 | ADR-028     |
| SP-FE-2G | `/collaboration` (retrofit) | `CollaborationCanvas`      | FE-PGS-031 | ADR-028     |

### Geimplementeerde componenten

| Sprint   | Component                          | Feature-ID  | Beschrijving                                              |
| -------- | ---------------------------------- | ----------- | --------------------------------------------------------- |
| SP-FE-2C | `CouncilVerdictTimeline`           | FE-PGS-017  | Audit-trail tijdlijn met SHA-256 hash chain               |
| SP-FE-2C | `HashChainVisualizer` (integratie) | FE-PGS-018  | Visuele hash-chain validatie in CouncilDashboard          |
| SP-FE-2D | `alert-dialog` (Radix wrapper)     | FE-CMP-008a | Herbruikbare delete-confirm dialog                        |
| SP-FE-2D | `useKnowledgeDocuments` hook       | FE-PGS-019  | Tenant-scoped React Query hook voor RAG-documenten        |
| SP-FE-2D | `ContextInjectionPanel` integratie | FE-CMP-008a | Panel in AgentDetailsFlyout Overview tab                  |
| SP-FE-2F | `PranaGauge`                       | FE-PGS-024  | Recharts RadialBarChart voor Prana-balans                 |
| SP-FE-2F | `A2AContractFlow`                  | FE-PGS-025  | XYFlow state-machine diagram voor A2A contracts           |
| SP-FE-2F | `ShadowCEOAlertFeed`               | FE-PGS-026  | Alert-feed met status-\* severity tokens                  |
| SP-FE-2F | `useShadowCEOStore`                | FE-PGS-026  | Zustand store voor governance-alerts                      |
| SP-FE-2G | `ConsentToggle`                    | FE-CMP-041  | AVG Art. 7 consent toggle met pending state               |
| SP-FE-2G | `useDigitalTwinProfile`            | FE-PGS-027  | React Query hook voor twin-profiel                        |
| SP-FE-2G | `OODATimeline`                     | FE-CMP-042  | Stateless 4-step OODA indicator                           |
| SP-FE-2G | `TraceStepList`                    | FE-CMP-043  | Step-list met status-\* tokens, hash-badge, toggle-detail |

### Dark-mode tokens (ADR-028 design system)

Alle Phase 2 componenten gebruiken:

- Achtergrond: `bg-slate-950` (page), `bg-slate-900` (cards), `bg-slate-800` (interactive)
- Tekst: `text-slate-100` (primary), `text-slate-400` (secondary)
- Status-tokens: `bg-status-success/20 text-status-success`, `bg-status-error/20 text-status-error`, `bg-status-warning/20 text-status-warning`, `bg-status-info/20 text-status-info`
- Borders: `border-slate-800`, `border-slate-700`

### Navigatie (BusinessSidebar, 16 items na SP-FE-2G + ADR-028 afsluiting)

```text
Dashboard, Agents, Automatiseringen, Planning, Kennis,
AI Council, HITL, Tool Broker (/tools), Compliance,
Prana (/prana), A2A Contracts (/prana/contracts),
Shadow CEO (/shadow-ceo), Digital Twin (/digital-twin),
Audit Logs (/tool-audit-logs), Collaboration (/collaboration), Developer
```

### Backend scopes toegevoegd (SP-FE-2F Dag 4)

Geregistreerd in `src/core/auth/scopes.py` + `src/core/auth/auth_service.py`:

- `PRANA_READ` -- leestoegang Prana Economy
- `PRANA_MANAGE` -- mutatietoegang Prana Economy
- `GOVERNANCE_READ` -- leestoegang Shadow CEO + governance-alerts
- `twin:read` -- leestoegang Digital Twin (toegevoegd aan `authStore.ts`)

### PermissionGate wiring (SP-FE-2F gaps gesloten, 2026-06-30)

Routes in `frontend/src/App.tsx` beveiligd met scope-gebaseerde `PermissionGate`:

| Route              | requiredScope     | Fallback              |
| ------------------ | ----------------- | --------------------- |
| `/prana`           | `prana:read`      | redirect `/dashboard` |
| `/prana/contracts` | `prana:read`      | redirect `/dashboard` |
| `/shadow-ceo`      | `governance:read` | redirect `/dashboard` |
| `/digital-twin`    | `twin:read`       | redirect `/dashboard` |

`viewer`-rol mist `governance:read` en `twin:read` -- wordt correct doorgestuurd naar dashboard.

---

## Alternatives

- **Isolated Pages / Popup-centric Workflow (Legacy Phase 1)**:
  - _Rejected_: Sticking to legacy separated `/workflows` and `/focus-builder` pages with heavy modal usage. This was rejected because user research confirms that interrupting the user's focus with blocking modals and page transitions degrades usability and reduces task completion speed.

## Consequences

- **Positive**:
  - **Absolute Parity & Design Conformity**: The frontend becomes a premium, highly cohesive representation of SanskritiSetu's advanced OS backend, strictly aligned with verified brainstorm prototypes.
  - **Radical Transparency**: Users can audit everything from token spend, inter-agent contracts, and board decisions to the cryptographically secured SHA-256 hash chains.
  - **Premium AX (Agentic Experience)**: Visually engaging real-time components (XYFlow net, YJS collaboration, steerable HITL) elevate the product above standard chat UIs.
- **Negative/Risks**:
  - **Refactoring Debt**: Sprints 1, 2, and 3 must be retrofitted to migrate legacy layouts to the new 3-panel architecture.
  - **Performance Overhead**: Heavy use of XYFlow (across Org Charts and Collaborative Canvas) and YJS real-time socket connections must be carefully managed using code-splitting and memoization.
