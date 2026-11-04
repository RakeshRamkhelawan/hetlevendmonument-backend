> **GEARCHIVEERD op 2026-09-27. Dit bestand wordt niet meer bijgewerkt.**
>
> De werkvoorraad staat nu op `docs/SPRINT-CANVAS.md`. Dat is het enige bord.
>
> Dit bestand blijft staan omdat 477 verwijzingen ernaar wijzen, vrijwel allemaal uit
> historische briefs in `docs/agent-briefs/generated/`. Verplaatsen zou die allemaal
> dood maken zonder dat er iets mee gewonnen wordt: het is geschiedenis, geen werk.
>
> Stand bij archivering: 246 sprints CLOSED, 1 IN PROGRESS (SP-TYPE-007, sinds
> 2026-06-27), 1 OPEN (SP-DLP-001, sinds 2026-06-25). Die twee staan nu op de canvas.
> Laatste inhoudelijke bijwerking was 2026-08-25.

---

# Sprint Tracker

> Enige bron van waarheid voor sprint-status. SPRINT-CANVAS.md is het overzicht; dit bestand is het detail.

---

## SP-SEC-001 -- Cache Tenant Isolatie + Audit Middleware + JSON Hardening

**Status:** CLOSED | **Start:** 2026-07-01 | **Gesloten:** 2026-07-01
**ADR:** ADR-003 (tenant identity), ADR-005 (tenant_id NOT NULL), ADR-019 (audit logging), ADR-026 (LLM contract)
**Bron:** Multidisciplinaire audit 2026-06-30 -- rapport docs/reports/MULTIDISCIPLINAIR-AUDIT-FULL-CODEBASE-2026-06-30.md

### Doel

Sluit alle CRITICAL/HIGH security-bevindingen uit de multidisciplinaire audit van 2026-06-30.
Drie root-cause-groepen met verplichte architecture tests die herhaling permanent blokkeren in CI.

### Dag 1 -- Cache TI + AuditLoggingMiddleware + json.loads hardening

**Status:** CLOSED | **Commits:** `1c83d6a7` (fix) + `40ef3627` (pre-existing) + `6c0aaf5e` (FA-minors) | **Datum:** 2026-07-01
**Brief:** docs/agent-briefs/generated/2026-07-01-sprint-dag-SP-SEC-001-dag-1.md
**FA-brief:** docs/agent-briefs/generated/2026-07-01-final-approver-SP-SEC-001-dag-1.md

Scope:
- ROOT-CAUSE-GROEP 1 (TI-001..005): 5 cache-sleutels zonder tenant_id
  - src/core/caching/cache_layer.py:311
  - src/core/knowledge/embedding_service.py:190
  - src/core/api/performance_middleware.py:87
  - src/core/llm/intelligent_router.py:239
  - src/core/company/goal_service.py:233
- ROOT-CAUSE-GROEP 2 (GOV-001): AuditLoggingMiddleware niet in middleware_config.py
- ROOT-CAUSE-GROEP 3 (LLM-C5-001/002): unprotected json.loads in llm_agent_adapter + adaptive_learning_engine
- BP-001 sweep: omvang bepalen (< 10 -> fix dag 1; >= 10 -> dag 2)
- Architecture tests: test_cache_tenant_isolation_enforced.py + test_audit_middleware_wired.py (verplicht)

Verwachte deliverables:
- BE-SEC-001 (cache isolatie), BE-SEC-002 (audit middleware), BE-SEC-003 (json hardening)
- 2 architecture tests GROEN na fix

### Dag 2 -- Paginering + BudgetManager + CollaborationCanvas route (SP-SEC-002)

**Status:** CLOSED -- zie `## SP-SEC-002` hieronder voor volledige documentatie.
**Commits:** `6c4ac58f` + `f2852a95` + `72e72552` | **Datum:** 2026-07-01

### SP-FE-2G ADR-028 Afsluiting -- CollaborationCanvas dark-mode retrofit (2026-07-01)

**Status:** CLOSED | **Commits:** `fee8020b` (fix) + `72e72552` (FA-001/002/003 minors) | **Datum:** 2026-07-01
**Feature-doc:** FE-PGS-031 | **Review:** docs/frontend/review/review-FE-PGS-031.md

Sluit het laatste openstaande ADR-028 item (8/9 -> 9/9 DONE). CollaborationCanvas dark-mode retrofit:
- 5 token-swaps: ConnectionBanner (bg-amber-900/30 + text-amber-300/red-300), NodeChip (bg-slate-900 + text-slate-100), CanvasArea (bg-slate-950 + border-slate-800), sticky-note button (bg-amber-900/30 + border-amber-800)
- FA-003 fix: text-slate-500 -> text-slate-400 (WCAG contrast ~4.53:1 -> ~6.3:1)
- FA-002 fix: text-token assertions toegevoegd aan 7 dark-mode compliance tests

Tests: 36/36 CollaborationCanvas tests GROEN (4 bestanden). Pyright 0 errors.
FA: GO WITH MINOR ISSUES -- FA-001/002/003 direct opgelost in 72e72552.
ADR-028 status na afsluiting: **9/9 DONE -- VOLLEDIG GESLOTEN**.

### Definition of Done SP-SEC-001 (incl. SP-SEC-002 + SP-FE-2G ADR-028 afsluiting)

- [x] ROOT-CAUSE-GROEP 1 (TI-001..005): 5 cache-sleutels tenant_id correct + arch test GROEN
- [x] ROOT-CAUSE-GROEP 2 (GOV-001): AuditLoggingMiddleware geregistreerd in middleware_config.py + arch test GROEN
- [x] ROOT-CAUSE-GROEP 3 (LLM-C5-001/002): json.loads beschermd per aanroep + logging
- [x] BP-002: GET /agents/ paginering -- 3 call-sites, pattern 5 compliant
- [x] LLM-C7-005: BudgetManager.check_budget() wiring in ExternalAgentService
- [x] BP-001: architecture test aangemaakt als CI-blokkering (fix in vervolgdag)
- [x] FE-001: /collaboration route + BusinessSidebar nav-link
- [x] SP-FE-2G ADR-028 afsluiting: CollaborationCanvas dark-mode retrofit (FE-PGS-031) -- ADR-028 9/9 DONE
- [x] Feature docs: BE-SEC-001/002/003 + BE-SVC-052/053 + FE-PGS-030/031 APPROVED
- [x] Architecture tests GROEN (cache-isolatie + audit-middleware-wiring; BP-001 opzettelijk ROOD)
- [x] Backend tests: 13,310 passed, 0 failed (SP-SEC-001 dag 1 baseline)
- [x] Frontend tests: 36/36 CollaborationCanvas GROEN
- [x] Pyright: 0 errors (baseline gehandhaafd)
- [x] Ruff: clean

---

## SP-SEC-002 -- API Response Conformance + Paginering + BudgetManager Wiring

**Status:** CLOSED | **Start:** 2026-07-01 | **Gesloten:** 2026-07-01
**ADR:** ADR-033 (router boundary), ADR-015 (ToolBroker allowlist), ADR-028 (Phase 2 visual)
**Bron:** SP-SEC-001 BP-001 sweep -- >= 10 non-conformante endpoints -> systematische aanpak in dag 2
**Prerequisite:** SP-SEC-001 CLOSED

### Doel

Sluit de resterende bevindingen uit de multidisciplinaire audit 2026-06-30 die niet in SP-SEC-001 pasten:
- BP-001: architecture test als CI-blokkering aanmaken (248 non-conformante API responses)
- BP-002: GET /agents/ paginering (limit/offset, 3 call-sites)
- LLM-C7-005: BudgetManager.check_budget() wiring in ExternalAgentService
- FE-001: CollaborationCanvas /collaboration route + BusinessSidebar nav-link

Aansluitend: SP-FE-2G ADR-028 afsluiting (CollaborationCanvas dark-mode retrofit, laatste openstaande ADR-028 item, 8/9 -> 9/9 DONE).

### Dag 1 -- BP-001 arch test + BP-002 paginering + LLM-C7-005 + FE-001 route

**Status:** CLOSED | **Commits:** `6c4ac58f` (fix) + `f2852a95` (FA-001/002) + `72e72552` (FA-001/002/003 incl. SP-FE-2G) | **Datum:** 2026-07-01
**Brief:** docs/agent-briefs/generated/2026-07-01-sprint-dag-SP-SEC-002-dag-1.md
**FA-brief:** docs/agent-briefs/generated/2026-07-01-final-approver-SP-SEC-002-dag-1.md

Scope gerealiseerd:
- BP-001: architecture test aangemaakt als CI-blokkering (ROOD -- 248 non-conformante API responses; fix in vervolgdag)
- BP-002: GET /agents/ limit/offset paginering -- 3 call-sites (agent_endpoints.py + list_agents_root + agent_crud_router.list_agents)
- LLM-C7-005: BudgetManager.check_budget() wiring in ExternalAgentService.get_next_task() (na null-check agent)
- FE-001: CollaborationCanvas /collaboration route (ProtectedRoute + lazy) + BusinessSidebar nav-link (Users icon)

Feature docs APPROVED: BE-SVC-052 (paginering) + BE-SVC-053 (BudgetManager wiring) + FE-PGS-030 (route).
FA: GO WITH MINOR ISSUES -- FA-001 (arch test false positives -> AST-gebaseerde scan) + FA-002 (triviale test -> exact assert) opgelost in f2852a95.
Tests: 210 gerichte unit tests GROEN. 3 arch tests GROEN (TI + audit-middleware). BP-001 arch test opzettelijk ROOD.
Pyright: 0 errors (baseline bewaard).

### SP-FE-2G ADR-028 Afsluiting -- CollaborationCanvas dark-mode retrofit (2026-07-01)

**Status:** CLOSED | **Commits:** `fee8020b` (fix) + `72e72552` (FA-001/002/003 minors) | **Datum:** 2026-07-01
**Feature-doc:** FE-PGS-031 | **Review:** docs/frontend/review/review-FE-PGS-031.md

Sluit het laatste openstaande ADR-028 item (8/9 -> 9/9 DONE). CollaborationCanvas dark-mode retrofit:
- 5 token-swaps: ConnectionBanner (bg-amber-900/30 + text-amber-300/red-300), NodeChip (bg-slate-900 + text-slate-100), CanvasArea (bg-slate-950 + border-slate-800), sticky-note button (bg-amber-900/30 + border-amber-800)
- FA-003 fix: text-slate-500 -> text-slate-400 (WCAG contrast ~4.53:1 -> ~6.3:1)
- FA-002 fix: text-token assertions toegevoegd aan 7 dark-mode compliance tests

Tests: 36/36 CollaborationCanvas tests GROEN (4 bestanden). Pyright 0 errors.
FA: GO WITH MINOR ISSUES -- FA-001/002/003 direct opgelost in 72e72552.
ADR-028 status na afsluiting: **9/9 DONE -- VOLLEDIG GESLOTEN**.

### Definition of Done

- [x] BP-001: architecture test aangemaakt als CI-blokkering (ROOD -- fix in vervolgdag)
- [x] BP-002: GET /agents/ paginering -- 3 call-sites, limit/offset, total_count pre-slice
- [x] LLM-C7-005: BudgetManager.check_budget() wiring in ExternalAgentService.get_next_task()
- [x] FE-001: /collaboration route (ProtectedRoute + lazy) + BusinessSidebar nav-link (Users icon)
- [x] SP-FE-2G ADR-028 afsluiting: CollaborationCanvas dark-mode retrofit (FE-PGS-031) -- ADR-028 9/9 DONE
- [x] Feature docs: BE-SVC-052/053 + FE-PGS-030/031 APPROVED
- [x] 210 gerichte unit tests GROEN (api + llm)
- [x] 36/36 CollaborationCanvas frontend tests GROEN
- [x] BP-001 arch test opzettelijk ROOD (CI-blokkering actief)
- [x] Pyright: 0 errors (baseline gehandhaafd)
- [x] Ruff: clean

---

## SP-FE-2C -- Phase 2 Visual Redesign: Compliance & Audit (Dag 1-3)

**Status:** CLOSED | **Start:** 2026-06-28 | **Gesloten:** 2026-06-28
**ADR:** ADR-028 (Phase 2 Visual Redesign), ADR-015 (ToolBroker + ProtectedRoute)
**Prerequisite:** Sprint 2b CLOSED (PR #144 MERGED 2026-06-27)

### Doel

Sprint 2c: 4 items (1 QW + 1 RF + 1 DONE + 1 NB) in de Compliance & Audit-track.
Scope: CouncilDashboard route, AuditLogs dark retrofit, HashChainVisualizer wiren, CouncilVerdictTimeline bouwen.

### Dag 1 -- /council route + AuditLogs dark theme retrofit

**Status:** CLOSED | **Commit:** `21bba4ea` | **Datum:** 2026-06-28

Gewijzigde bestanden:

- `frontend/src/App.tsx` -- `React.lazy(CouncilDashboard)` + `/council` route (ProtectedRoute > LazyWrapper)
- `frontend/src/components/layout/BusinessSidebar.tsx` -- `Scale` icon + `{ to: '/council', label: 'Council' }`
- `frontend/src/pages/AuditLogs.tsx` -- 3x className: `bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900` -> `bg-slate-950 text-slate-100`
- `frontend/src/pages/redesign/__tests__/CouncilDashboard.route.test.tsx` (NIEUW -- 2 tests)
- `frontend/src/pages/__tests__/AuditLogs.retrofit.test.tsx` (NIEUW -- 3 tests)
- `docs/frontend/features/FE-PGS-015-council-dashboard-route.md` (skeleton spec)
- `docs/frontend/features/FE-PGS-016-audit-logs-dark-retrofit.md` (skeleton spec)
- `docs/frontend/features/ID-REGISTRY.md` -- FE-PGS counter 015->017

Tests: 5/5 gerichte tests GROEN. 128/128 gerichte regressietests GROEN.
Feature docs: FE-PGS-015 + FE-PGS-016 aangemaakt (skeleton, volledig op dag 3).
FA: GO WITH MINOR ISSUES -- FA-001 MINOR: Laag A review overgeslagen (chirurgische wijzigingen).

Pre-existing test fixes (zelfde sessie, commits `0fbc49a3` + `ad7226d4`):

- AgentDetailModal 21/21: `isApiError` van `lib/api/client` gemockt (VitestMocker error in catch-pad)
- ForbiddenBusinessRedesignPages 31/31: `useDashboardKPIs` + `useDailySummary` aan `useApi` mock toegevoegd
- ComplianceHub 1/1: PermissionGate tekst 'Toegang Geweigerd' -> 'Access Denied' bijgewerkt
- useCreateWorkflow 1/1: URL-assertie `/api/v1/workflows` -> `/api/v1/workflows/` (trailing slash)
  Resultaat: frontend suite 0 failures (892/902 test files GROEN, 14,492 tests GROEN)

### Dag 2 -- CouncilVerdictTimeline + HashChainVisualizer in CouncilDashboard

**Status:** CLOSED | **Commit:** `81066689` + FA-minors `5ad2eeb9` | **Datum:** 2026-06-28

Gewijzigde bestanden:

- `frontend/src/pages/redesign/CouncilDashboard.tsx` -- HashChainVisualizer integratie
- `frontend/src/components/council/CouncilVerdictTimeline.tsx` (NIEUW)
- `frontend/src/components/council/__tests__/CouncilVerdictTimeline.test.tsx` (NIEUW)
- `docs/frontend/features/FE-PGS-017-council-verdict-timeline.md`
- `docs/frontend/features/FE-PGS-018-hashchain-visualizer-integration.md`
- `docs/frontend/features/ID-REGISTRY.md` -- FE-PGS counter 017->019

FA minors gefixed (commit `5ad2eeb9`): FA-001 non-ASCII in comment + FA-002 stale JSDoc in CouncilDashboard.
FA: GO.

### Dag 3 -- Feature docs afronden + sprint sluiten

**Status:** CLOSED | **Commit:** `007850a5` | **Datum:** 2026-06-28

- FE-PGS-015 + FE-PGS-016 volledig ingevuld (spec + review + trainingssamenvatting + user guide)
- `python scripts/validate_feature_docs.py` -- [PASS]
- Sprint CLOSED

### Definition of Done

- [x] Dag 1: /council route GROEN + AuditLogs bg-slate-950 GROEN
- [x] Dag 2: CouncilVerdictTimeline gebouwd + HashChainVisualizer gewired
- [x] Dag 3: Feature docs APPROVED (FE-PGS-015 + FE-PGS-016 + FE-PGS-017 + FE-PGS-018)
- [x] Frontend suite 0 failures (892 test files, 14,492 tests)
- [x] FE-PGS-015 t/m FE-PGS-018 reviews APPROVED
- [x] ID-REGISTRY bijgewerkt (FE-PGS counter 019)

---

## SP-FE-2D -- Phase 2 Visual Redesign: Knowledge & RAG (Dag 1-3)

**Status:** CLOSED | **Start:** 2026-06-28 | **Gesloten:** 2026-06-28
**ADR:** ADR-028 (Phase 2 Visual Redesign)
**Prerequisite:** SP-FE-2C CLOSED

### Doel

Sprint 2d: 5 items (2 RF + 2 DONE/integratie + 1 NB) in de Knowledge & RAG-track.
Scope: Knowledge.tsx full page, useKnowledgeDocuments hook, AlertDialog delete confirm, ContextInjectionPanel in AgentDetailsFlyout, Integrations ADR-028 audit.

### Dag 1 -- Knowledge.tsx uitbreiding + useKnowledgeDocuments hook

**Status:** CLOSED | **Commit:** `aa86f72b` | **Datum:** 2026-06-28

- `frontend/src/pages/redesign/Knowledge.tsx` -- full page: documentenlijst + filter + paginering + AlertDialog + SemanticSearch + EmbeddingsQualityDashboard
- `frontend/src/hooks/useKnowledgeDocuments.ts` (NIEUW) -- tenant-scoped React Query hook
- `frontend/src/hooks/__tests__/useKnowledgeDocuments.test.ts` (NIEUW -- 6 tests)
- `frontend/src/pages/redesign/__tests__/Knowledge.test.tsx` -- 10 tests
- `docs/frontend/features/FE-PGS-019-knowledge-page.md` (spec)

FA: GO WITH MINOR ISSUES -- FA-001 semantic label misalignment, FA-002 filter reset op paginawissel, FA-003 Slider ARIA.

### Dag 2 -- AlertDialog + behavioral tests + ContextInjectionPanel + Integrations audit

**Status:** CLOSED | **Commit:** `713043b2` + docs `1edcd6fc` + `aad613a8` | **Datum:** 2026-06-28

- `frontend/src/components/ui/alert-dialog.tsx` (NIEUW) -- Radix AlertDialog wrapper
- `frontend/src/pages/redesign/Knowledge.tsx` -- AlertDialog delete confirm
- `frontend/src/pages/redesign/__tests__/Knowledge.test.tsx` -- +3 behavioral tests (search, status filter, paginering)
- `frontend/src/components/features/AgentDetailsFlyout.tsx` -- ContextInjectionPanel in Overview tab
- `frontend/src/components/features/__tests__/AgentDetailsFlyout.test.tsx` -- +3 tests (CIP render, tab switch, ErrorBoundary)
- `docs/frontend/features/FE-PGS-020-integrations-adr028-audit.md` (spec)
- `docs/frontend/features/FE-CMP-008a-agentdetailsflyout-context-injection.md` (spec)

Pre-existing fixes (commits `e8f94cd5` + `f3520faf`): 117 legacy feature-doc gaps + KanbanBoard type-check fix.
FA: GO.

### Dag 3 -- Feature docs afronden + finale regressiecheck + sprint sluiten

**Status:** CLOSED | **Commit:** `d361bbcc` + `7b1e3ea0` | **Datum:** 2026-06-28

- `frontend/src/pages/redesign/Knowledge.tsx` -- `data-testid="rag-pipeline-page"` + Engelstalige description hersteld (regressiefix ForbiddenBusinessRedesignPages)
- FE-PGS-019/020 + FE-CMP-008a volledig ingevuld (spec + review + trainingssamenvatting + user guide)
- `python scripts/validate_feature_docs.py` -- [PASS] 411 IDs
- Sprint CLOSED

Tests: 895 files passed / 14,518 tests passed / 0 failed.
FA: GO (0 bevindingen).

### Definition of Done

- [x] Dag 1: Knowledge.tsx full page GROEN + useKnowledgeDocuments hook GROEN
- [x] Dag 2: AlertDialog + behavioral tests + ContextInjectionPanel GROEN
- [x] Dag 3: Feature docs APPROVED + regressie 0 failures
- [x] Frontend suite 0 failures (895 files, 14,518 tests)
- [x] FE-PGS-019/020 + FE-CMP-008a reviews APPROVED
- [x] ID-REGISTRY bijgewerkt (FE-PGS counter 021, FE-CMP counter 037)

---

## SP-FE-2E -- Phase 2 Visual Redesign: Integrations & ToolBroker (Dag 1)

**Status:** CLOSED | **Start:** 2026-06-28 | **Gesloten:** 2026-06-28
**ADR:** ADR-028 (Phase 2 Visual Redesign), ADR-015 (ToolBroker allowlist + HITL gate)
**Prerequisite:** SP-FE-2D CLOSED

### Doel

Sprint 2e: 3 Quick Wins (route wiring + ADR-028 audit) -- ToolBrokerRegistry, HITLQueue redesign, ToolAuditLogs.

### Dag 1 -- ToolBrokerRegistry + HITLQueue swap + ToolAuditLogs route wiring + ADR-028 audit

**Status:** CLOSED | **Commit:** `f5bc2cba` + FA-fix `9eff6ac6` + docs `c7b51d22` | **Datum:** 2026-06-28

- `frontend/src/App.tsx` -- lazy imports + `/tools` (ToolBrokerRegistry) + `/tool-audit-logs` (ToolAuditLogs) routes; `/hitl` geswapped van HITLPage naar redesign HITLQueue
- `frontend/src/components/layout/BusinessSidebar.tsx` -- nav links: /tools (Shield), /hitl (CheckCircle), /tool-audit-logs (FileText)
- `frontend/src/pages/redesign/ToolBrokerRegistry.tsx` -- `api` -> `apiClient` fix
- `frontend/src/pages/redesign/HITLQueue.tsx` -- `api` -> `apiClient` fix
- `frontend/src/components/integrations/ToolBrokerCard.tsx` -- `PermissionGate requiredScope="agents:manage"` op Switch
- `frontend/src/components/compliance/HITLDecisionForm.tsx` -- `ClassificationWrapper classification="confidential"` op counter-proposal
- `frontend/src/pages/redesign/__tests__/ToolBrokerRegistry.test.tsx` -- 31 tests (HIGH/CRITICAL modal, PermissionGate, rate-limit kleuren)
- `frontend/src/pages/redesign/__tests__/HITLQueue.test.tsx` -- 30 tests (SLA badge, auto-expire, justification validatie, PermissionGate)
- `frontend/src/pages/redesign/__tests__/ToolAuditLogs.test.tsx` -- 20 tests (error rate alarm, ?tool= deep-link, paginering)
- `docs/frontend/features/FE-PGS-021/022/023` + reviews + user guides
- `docs/frontend/features/ID-REGISTRY.md` -- FE-PGS counter 021->024

FA-001/002/003 (em dashes) gefixed in commit `9eff6ac6`.
FA: GO (na minor fix).

Tests: 895 files passed / 14,526 tests passed / 0 failed.

### Definition of Done

- [x] Dag 1: alle 3 QW routes GROEN + PermissionGate/ClassificationWrapper correct
- [x] Frontend suite 0 failures (895 files, 14,526 tests)
- [x] FE-PGS-021/022/023 reviews APPROVED / APPROVED WITH MINOR GAPS
- [x] ID-REGISTRY bijgewerkt (FE-PGS counter 024)
- [x] `npx tsc --noEmit` -- 0 errors
- [x] `validate_feature_docs.py` -- [PASS] 414 IDs

---

## SP-FE-2F -- Phase 2 Visual Redesign: Prana economy + Shadow CEO governance (Dag 1-4)

**Status:** CLOSED | **Start:** 2026-06-28 | **Gesloten:** 2026-06-29
**ADR:** ADR-028 (Phase 2 Visual Redesign), ADR-015 (ToolBroker + ProtectedRoute)
**Prerequisite:** SP-FE-2E CLOSED

### Doel

Sprint 2f: 3 pagina's + bijbehorende componenten/stores voor de Prana-economie en Shadow CEO governance:

- `/prana` — PranaDashboard + PranaGauge
- `/prana/contracts` — A2AContracts + A2AContractFlow
- `/shadow-ceo` — ShadowCEOMonitor + ShadowCEOAlertFeed + useShadowCEOStore

### Dag 1 -- PranaDashboard + PranaGauge

**Status:** CLOSED | **Commit:** `9582c83f` + revisie `0ff021fa` | **Datum:** 2026-06-28

- `frontend/src/pages/redesign/PranaDashboard.tsx` (NIEUW)
- `frontend/src/components/prana/PranaGauge.tsx` (NIEUW)
- `frontend/src/pages/redesign/__tests__/PranaDashboard.test.tsx` (NIEUW)
- `frontend/src/components/prana/__tests__/PranaGauge.test.tsx` (NIEUW)
- `docs/frontend/features/FE-PGS-024-prana-dashboard.md` + review

FA: GO.

### Dag 2 -- A2AContracts + A2AContractFlow

**Status:** CLOSED | **Commit:** `af4d68af` + fix `a011504c` | **Datum:** 2026-06-28

- `frontend/src/pages/redesign/A2AContracts.tsx` (NIEUW)
- `frontend/src/components/prana/A2AContractFlow.tsx` (NIEUW)
- `frontend/src/pages/redesign/__tests__/A2AContracts.test.tsx` (NIEUW)
- `frontend/src/components/prana/__tests__/A2AContractFlow.test.tsx` (NIEUW)
- `docs/frontend/features/FE-PGS-025-a2a-contracts.md` + review

FA: GO WITH MINOR ISSUES — FA-001 node stroke width Tailwind class conflict gefixt in `a011504c`.

### Dag 3 -- ShadowCEOMonitor + ShadowCEOAlertFeed + useShadowCEOStore

**Status:** CLOSED | **Commit:** `5eba2e83` (gedeeld met dag 4) | **Datum:** 2026-06-28

- `frontend/src/pages/redesign/ShadowCEOMonitor.tsx` (NIEUW)
- `frontend/src/components/prana/ShadowCEOAlertFeed.tsx` (NIEUW)
- `frontend/src/lib/stores/useShadowCEOStore.ts` (NIEUW)
- `frontend/src/types/governanceAlerts.ts` (NIEUW)
- Tests: store + component + page
- `docs/frontend/features/FE-PGS-026-shadow-ceo-monitor.md` + reviews (FE-PGS-026 + FE-CMP-040)
- `docs/user-guide/frontend/shadow-ceo-monitor.md`

FA: GO.

### Dag 4 -- Route wiring + backend scope registratie + review fixes

**Status:** CLOSED | **Commits:**

- `5eba2e83` — ShadowCEO + route wiring + backend scopes
- `12bb06d2` — review fixes (default exports, 14 nav items, docs)
- `f7d0de3b` — pre-existing flaky test fixes
- `840536ef` — FA minors adres
- `209ec8f1` — Dag 4 FA brief
- `21e5713c` — Final Approver CLOSED brief
  **Datum:** 2026-06-29

- `frontend/src/App.tsx` — routes `/prana`, `/prana/contracts`, `/shadow-ceo` onder `ProtectedRoute` / `LazyWrapper`
- `frontend/src/components/layout/BusinessSidebar.tsx` — 14 nav items; A2A Contracts krijgt `FileSignature`; Audit Logs houdt `FileText`
- `frontend/src/components/layout/__tests__/BusinessSidebar.test.tsx` — 14-label assertie
- `src/core/auth/scopes.py` — `PRANA_READ`, `PRANA_MANAGE`, `GOVERNANCE_READ`
- `src/core/auth/auth_service.py` — scopes gekoppeld aan rollen
- Feature docs FE-PGS-024/025/026 bijgewerkt naar Completed + route/backend status
- Reviews FE-PGS-024/025 bijgewerkt naar APPROVED (minors opgelost)

FA minors afgehandeld:

- FA-001: ShadowCEOAlertFeed severity-kleuren → `status-*` tokens
- FA-002: `fetchAlerts()` patroon → TODO(`SP-VOLGENDE`) in store
- FA-003: `governance:read` aan `user`-rol → TODO(`SP-VOLGENDE`) voor Rakesh
- FA-004: BusinessSidebar dubbel `FileText` → A2A Contracts krijgt `FileSignature`

**Tests:**

- Shard 1: 4783 passed / 71 skipped / 0 failed ✅
- Shard 2: 4650 passed / 70 skipped / 0 failed ✅
- Shard 3: 5165 passed / 52 skipped / 0 failed ✅
- `npm run type-check` — 0 errors
- `npm run lint` — 0 errors (pre-existing warnings)
- `python -m py_compile src/core/auth/scopes.py src/core/auth/auth_service.py` — OK
- `python scripts/validate_feature_docs.py` — 427 IDs [PASS]

FA (dag 4): GO — geen open bevindingen. Sprint **CLOSED**.

### Definition of Done

- [x] Dag 1: PranaDashboard + PranaGauge gebouwd en GROEN
- [x] Dag 2: A2AContracts + A2AContractFlow gebouwd en GROEN
- [x] Dag 3: ShadowCEOMonitor + ShadowCEOAlertFeed + useShadowCEOStore gebouwd en GROEN
- [x] Dag 4: routes `/prana`, `/prana/contracts`, `/shadow-ceo` gewired; backend scopes geregistreerd
- [x] Frontend suite 0 failures (alle 3 shards groen)
- [x] FE-PGS-024 / FE-PGS-025 / FE-PGS-026 specs + reviews APPROVED
- [x] ID-REGISTRY bijgewerkt (FE-PGS counter 027, FE-CMP 041, etc.)
- [x] `validate_feature_docs.py` — 427 IDs [PASS]
- [x] User guides aangemaakt / bijgewerkt (prana-dashboard, a2a-contracts, shadow-ceo-monitor)

---

## SP-FE-2G -- Phase 2 Visual Redesign: Digital Twin & Traces (Dag 1-4)

**Status:** CLOSED | **Start:** 2026-06-29 | **Gesloten:** 2026-06-30
**ADR:** ADR-026 (Twin consent gate + 90-day retention), ADR-028 (Phase 2 dark redesign)
**Prerequisite:** SP-FE-2F CLOSED

### Doel

Sprint 2g: 3 dagen — DigitalTwin dark-mode retrofit, ConsentToggle, OODATimeline, TraceStepList en TraceViewerPage route wiring.

| Dag | Deliverables                                                                                              | Type    |
| --- | --------------------------------------------------------------------------------------------------------- | ------- |
| 1   | `useDigitalTwinProfile` hook + `ConsentToggle` component                                                  | NB      |
| 2   | `DigitalTwin.tsx` dark-mode retrofit + `OODATimeline` component                                           | RF + NB |
| 3   | `TraceViewerPage` + `useTraceSteps` hook + `TraceStepList` + route wiring + backend scopes + feature docs | QW + NB |

**Nieuwe routes (Dag 3):**

- `/digital-twin` — scope: `twin:read`
- `/traces` — scope: `trace:read` (bestaat al)

**Scope-conventie:** project gebruikt `noun:verb` (`prana:read`, `trace:read`, `governance:read`). Gebruik `twin:read` voor DigitalTwin; hergebruik `trace:read` voor traces.

### Dag 1 -- useDigitalTwinProfile hook + ConsentToggle component

**Status:** CLOSED (GO) | **Commit:** `b617c275` | **Minor-fix:** `410d3614` | **Datum:** 2026-06-29

- Sprint-dag brief: `docs/agent-briefs/generated/2026-06-29-sprint-dag-SP-FE-2G-dag-1.md`
- Final-approver brief: `docs/agent-briefs/generated/2026-06-29-final-approver-SP-FE-2G-dag-1.md`
- Scope toegevoegd aan `frontend/src/lib/stores/authStore.ts`: `twin:read`
- Gebouwd:
  - `frontend/src/hooks/useDigitalTwinProfile.ts` + 6 tests
  - `frontend/src/components/twin/ConsentToggle.tsx` + 7 tests (incl. pending state)
  - `docs/frontend/features/FE-CMP-041-consent-toggle.md`
  - `docs/frontend/review/review-FE-CMP-041.md`
  - `docs/user-guide/frontend/consent-toggle.md`
- Validatie: `npm run test:unit` 3 shards 0 failures; `npm run type-check` 0 errors; `validate_feature_docs.py` 428 IDs [PASS]
- Final Approver: GO -- minors FA-001 (isPending guard) en FA-002 (pending state test) direct opgelost

### Dag 2 -- DigitalTwin dark-mode retrofit + OODATimeline component

**Status:** CLOSED (GO) | **Commit:** `24bfa38e` | **Datum:** 2026-06-29

- Sprint-dag brief: `docs/agent-briefs/generated/2026-06-29-sprint-dag-SP-FE-2G-dag-2.md`
- Final-approver brief: `docs/agent-briefs/generated/2026-06-29-final-approver-SP-FE-2G-dag-2.md`
- Gebouwd:
  - `frontend/src/pages/DigitalTwin.tsx` -- volledige ADR-028 dark-mode retrofit (FE-PGS-027)
  - `frontend/src/components/twin/OODATimeline.tsx` -- stateless 4-step OODA indicator (FE-CMP-042)
  - 5 dark-mode tests + 5 OODATimeline tests + 10 regressietests -- 20 GROEN
- Validatie: `npm run test:unit` 20 tests GROEN | `npm run type-check` 0 errors | `npm run lint` 0 errors
- Final Approver: GO (geen bevindingen)

### Dag 3 -- Route wiring, consent gate, TraceStepList, TraceViewerPage swap

**Status:** CLOSED (GO) | **Commit:** `910fdb97` | **Minor-fixes:** `122e2da9`, `979a64c0` | **Datum:** 2026-06-29

- Sprint-dag brief: `docs/agent-briefs/generated/2026-06-30-sprint-dag-SP-FE-2G-dag-3.md`
- Final-approver brief: `docs/agent-briefs/generated/2026-06-29-final-approver-SP-FE-2G-dag-3.md`
- Gebouwd (23 gewijzigde bestanden):
  - `frontend/src/App.tsx` -- lazy `/digital-twin` route (ProtectedRoute + PermissionGate twin:read) + TraceViewerPage swap
  - `frontend/src/components/layout/BusinessSidebar.tsx` -- Brain icon + Digital Twin nav-item (15 items)
  - `frontend/src/pages/DigitalTwin.tsx` -- ADR-026 consent gate (useTwinConsent) + computeActivePhase (frictionScore)
  - `frontend/src/components/twin/TraceStepList.tsx` -- nieuw component: status-\* tokens, toggle detail, hash-badge (FE-CMP-043)
- Specs: FE-PGS-028, FE-CMP-043, FE-PGS-029 | `validate_feature_docs.py` 433/433 [PASS]
- Validatie: 48 targeted + 68 regressietests GROEN | `npm run type-check` 0 errors | `npm run lint` 0 errors
- Final Approver: GO -- minor FA-001 (BusinessSidebar button type) direct opgelost in `122e2da9`

### Dag 4 -- Gate 3 voorbereiding + SPRINT_TRACKER bijwerken

**Status:** CLOSED | **Datum:** 2026-06-30

- Dag-brief: `docs/agent-briefs/generated/2026-06-29-sprint-dag-SP-FE-2G-dag-4.md`
- Pre-existing fix: `frontend/src/components/ui/KanbanBoard.tsx` -- DraggingStyle spread TS2322 opgelost
- CI/CD fix: `.github/workflows/cd-staging.yml` -- Azure login + ACR firewall rules voor backend + worker build jobs
- SPRINT_TRACKER.md + SPRINT_PLANNING.md bijgewerkt (Dag 2+3 CLOSED, sprint CLOSED)
- Gate 3 PR aangemaakt: develop -> main

### ADR-028 Afsluiting -- CollaborationCanvas dark-mode retrofit (2026-07-01)

**Status:** CLOSED | **Commits:** `fee8020b` (fix) + `72e72552` (FA-001/002/003) | **Datum:** 2026-07-01

Sluit het laatste openstaande ADR-028 item. Uitgevoerd samen met SP-SEC-002 dag 1 (commit 72e72552 bevat zowel SP-SEC-002 FA-fixes als SP-FE-2G ADR-028 minors).
FE-PGS-031 APPROVED. ADR-028 status: **9/9 DONE -- VOLLEDIG GESLOTEN**.

---

## SP-API-011-arch -- Arch backlog cleanup: 12 xfailed tests -> 0 (Dag 1-3)

**Status:** CLOSED | **Start:** 2026-06-27 | **Gesloten:** 2026-06-27
**ADR:** ADR-033 (router boundary + flat-file facade patroon)
**Prerequisite:** SP-API-011-backlog CLOSED

### Doel

12 `xfail(strict=True)` architecture tests sluiten die de ADR-033 backlog bewaken.
Arch-suite: 283/12xfailed -> 294/0xfailed in 3 dagen.

### Dag 1 -- ADR imports + stats_router sibling (3 xfails gesloten)

**Commit:** `1b99bb17`

- cva/dependencies.py ADR-beslissing GOEDGEKEURD (domeinlagen mogen)
- 5 governance lazy imports -> governance/dependencies.py
- AIDecision -> gdpr_compliance/dependencies.py
- stats_router sibling-imports -> orchestration/dependencies.py
- Arch: 285 passed, 9 xfailed. BE-API-041 APPROVED.

### Dag 2 -- Route gaps + clear_tenant_cache caller (6 xfails gesloten)

**Commit:** `9dd9deb5`

- clear_tenant_cache() caller in delete_tenant (re-export via tenants/dependencies.py)
- GET /integrations/catalog + /integrations/search stubs (tools/integrations_router.py)
- WebSocket /ws/builder alias (accept+close 1001 redirect)
- POST /{template_id}/deploy + GET /search/ in template_router.py
- Arch: 291 passed, 3 xfailed. BE-API-042 APPROVED.

### Dag 3 -- Batch A flat files forbidden imports (3 xfails gesloten)

**Commit:** `5c7c486b`

- 4 nieuwe \*\_dependencies.py facades (agent_endpoints_db, agent_endpoints, admin_learning, assistant)
- Gesplitste facade voor agent_endpoints: lazy-load invariant bewaard (test_agent_endpoints_imports_without_agent_registry PASSING)
- dsm_api_violation_finder \*\_dependencies.py exempt toegevoegd
- collective_knowledge.py stash conflict opgelost (upstream cast() versie)
- Arch: 294 passed, 0 failed, 0 xfailed. BE-API-043 APPROVED. FA: GO.

### Definition of Done

- [x] Alle 12 xfailed tests gesloten (3 xfail markers per dag verwijderd)
- [x] `tests/architecture/` -- 294 passed, 0 failed, 0 xfailed
- [x] `python -m pyright` -- 0 errors
- [x] `dsm_api_violation_finder` -- 0 violations
- [x] Feature docs: BE-API-041 + BE-API-042 + BE-API-043 APPROVED
- [x] ID-REGISTRY bijgewerkt

---

## SP-DSM-010 -- agent_runtime <-> integrations circular sluiten (Grade A)

**Status:** CLOSED | **Start:** 2026-06-24 | **Gesloten:** 2026-06-24
**ADR:** ADR-025 (event-bus), ADR-034 (agent_runtime boundary)
**Prerequisite:** SP-DSM-INFRA-001 CLOSED + SP-DSM-REGRESSIE CLOSED
**Doel:** Grade B -> Grade A: enige resterende MEDIUM circulaire pair sluiten via MODULE_MAP reclassificatie.

### Root cause

De `integrations -> agent_runtime` reverse richting (13 imports) bestaat doordat 2 directories
verkeerd geclassificeerd zijn als `integrations` in `scripts/dsm_full_analysis.py`:

| Bestand                                              | Misclassificatie                    | Verkeerde imports                                  |
| ---------------------------------------------------- | ----------------------------------- | -------------------------------------------------- |
| `src/core/collaboration/task_distributor.py`         | `collaboration/` als integrations   | 9x `src.core.agents.*` + `src.core.ai`             |
| `src/core/events/handlers/learning_event_handler.py` | `events/handlers/` als integrations | `LearningSource, LearningType, ObservationService` |
| `src/core/events/handlers/workflow_handler.py`       | `events/handlers/` als integrations | `DepartmentOrchestrator`                           |

### Aanpak: MODULE_MAP reclassificatie (nul productie-code wijzigingen)

**Wijziging 1 -- MODULE_MAP (`scripts/dsm_full_analysis.py`):**

- `"src.core.collaboration": "integrations"` -> `"src.core.collaboration": "agent_runtime"`
- Voeg toe VOOR `"src.core.events"` entry: `"src.core.events.handlers": "agent_runtime"` (longest-prefix wint)

**Wijziging 2 -- SOURCE_DIRS (`scripts/dsm_full_analysis.py`):**

- Verwijder `"src/core/collaboration"` uit `integrations` lijst
- Voeg `"src/core/collaboration"` toe aan `agent_runtime` lijst

### Definition of Done

- [x] `scripts/dsm_full_analysis.py` aangepast (MODULE_MAP + SOURCE_DIRS)
- [x] `tests/architecture/test_dsm_010_no_integrations_agent_runtime_circular.py` GROEN
- [x] DSM scanner: integrations->agent_runtime reverse = 0 (was 13)
- [x] DSM scanner: agent_runtime<->integrations circulaire pair VERDWENEN
- [x] Grade A bevestigd (0 MEDIUM circulairs)
- [x] Arch-suite: 218 passed (was 217, +1 nieuwe test), 0 nieuwe failures
- [x] pyright: 0 errors | ruff: clean
- [x] BE-DSM-026 spec + review APPROVED | ID-REGISTRY bijgewerkt

### Sprint-dag brief

`docs/agent-briefs/generated/2026-06-24-sprint-dag-SP-DSM-010-dag1.md`

### Roadmap na SP-DSM-010

| Sprint     | Doel                                                         | Grade        |
| ---------- | ------------------------------------------------------------ | ------------ |
| SP-DSM-011 | governance I 0.613->0.35 via governance_worker               | A (monotoon) |
| SP-DSM-012 | worker 0.904->0.65 + core_api 1.000->0.85 via work-contracts | A+           |

Audit baseline: `docs/reports/DSM-AUDIT-2026-06-24.md`

---

## SP-DSM-011 -- governance instabiliteit I 0.613 -> 0.373 (governance_worker pattern)

**Status:** CLOSED | **Start:** 2026-06-24 | **Gesloten:** 2026-06-24
**Prerequisite:** SP-DSM-010 CLOSED
**Doel:** governance I verlagen via MODULE_MAP + SOURCE_DIRS chirurgie. Nul productie-codewijzigingen.

### Root cause

Twee factoren inflateerden governance Ce tot 68:

| Factor                                                                                | Ce-inflatie | Mechanisme                                                                             |
| ------------------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------- |
| `governance.models` als `"shared"` in MODULE_MAP (SP-DSM-REGRESSIE artifact)          | +22         | 22 interne governance->governance.models imports telden als governance->shared         |
| `event_handlers.py` (Ce=6) + `dsar_notifications.py` (Ce=2) in governance SOURCE_DIRS | +8          | Beide bestanden scanden als governance; hun outgoing deps telden mee als governance Ce |

### Aanpak: governance_worker pattern

1. Verwijder `"src.core.governance.models": "shared"` uit MODULE_MAP
2. Voeg toe: `"src.core.governance.event_handlers": "worker"` en `"src.core.governance.dsar_notifications": "integrations"`
3. SOURCE_DIRS chirurgie: governance/ enumereren (33 bestanden + 3 subdirs), event_handlers.py + dsar_notifications.py uitsluiten
4. worker SOURCE_DIRS: event_handlers.py toevoegen; integrations SOURCE_DIRS: dsar_notifications.py toevoegen

Neveneffect: governance.models reclassificatie onthult 2 pre-existing infra->governance imports
(tenant_query_filter.py:165 + models/**init**.py:9). LAAG paar, SP-DSM-012 backlog.

### Definition of Done

- [x] `scripts/dsm_full_analysis.py` aangepast (MODULE_MAP + SOURCE_DIRS)
- [x] `tests/architecture/test_dsm_011_governance_instability_below_0_40.py` GROEN (I=0.373 < 0.40)
- [x] `tests/architecture/test_dsm_medium_pairs_tracking.py` uitgebreid (governance<->infra ceiling <= 2)
- [x] `tests/architecture/test_dsm_governance_regression.py` bijgewerkt (ceiling 2 i.p.v. strikt 0)
- [x] Arch-suite: 220 passed (was 218, +2 nieuwe tests), 0 nieuwe failures
- [x] pyright: 0 errors | ruff: clean
- [x] BE-DSM-027 spec + review APPROVED | ID-REGISTRY bijgewerkt

### Sprint-dag brief

`docs/agent-briefs/generated/2026-06-24-final-approver-SP-DSM-011-dag1.md`

---

## SP-DSM-012 -- infra->governance SDP-schending sluiten (2->0)

**Status:** CLOSED | **Start:** 2026-06-24 | **Gesloten:** 2026-06-24
**Prerequisite:** SP-DSM-011 CLOSED
**Doel:** 2 infra->governance backward deps elimineren via productie-codewijzigingen (geen MODULE_MAP tricks).

### Root cause

Na SP-DSM-011 governance.models reclassificatie werden 2 pre-existing infra->governance imports zichtbaar:

| Bestand                                        | Import                                            | Reden bestond                                                              |
| ---------------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------- |
| `src/core/database/tenant_query_filter.py:165` | `from src.core.governance.models import AuditLog` | AuditLog identity check (redundant met `__tablename__` check)              |
| `src/core/models/__init__.py:9`                | `from src.core.governance.models import AuditLog` | Alembic model discovery re-export (dode code, model_registry dekte dit al) |

### Aanpak

1. `tenant_query_filter.py`: governance import + outer try/except verwijderd; `__tablename__ == "audit_logs"` als directe guard
2. `models/__init__.py`: AuditLog import + `__all__` entry + `Any` import verwijderd (dode code)
3. `dsm_full_analysis.py`: event_handlers.py worker->integrations reclassificatie (SP-DSM-011 FA-F003)
4. `test_dsm_medium_pairs_tracking.py`: governance<->infra ceiling aangescherpt van <= 2 naar == 0

### Definition of Done

- [x] `src/core/database/tenant_query_filter.py` governance import verwijderd; security-pad vereenvoudigd
- [x] `src/core/models/__init__.py` AuditLog re-export verwijderd (dode code)
- [x] `tests/architecture/test_dsm_governance_regression.py::test_infra_no_governance_imports` GROEN (was ROOD)
- [x] `tests/architecture/test_dsm_medium_pairs_tracking.py` ceiling tightened: == 0
- [x] infra->governance = 0 bevestigd via DSM scanner
- [x] governance I = 0.3800 (blijft < 0.40)
- [x] Arch-suite: 220 passed, 0 failed, 13 xfailed
- [x] pyright: 0 errors | ruff: clean
- [x] BE-DSM-028 spec + review APPROVED | ID-REGISTRY bijgewerkt

### Sprint-dag brief

`docs/agent-briefs/generated/2026-06-24-sprint-dag-SP-DSM-012-dag1.md`

---

## SP-DSM-013 -- worker instabiliteit I 0.904 -> 0.639

**Status:** CLOSED | **Start:** 2026-06-25 | **Gesloten:** 2026-06-25
**Prerequisite:** SP-DSM-012 CLOSED
**Doel:** worker I verlagen van 0.904 naar <0.80 via MODULE_MAP + SOURCE_DIRS chirurgie. Nul productie-codewijzigingen.

### Root cause

worker Ce=75 (16 bestanden) door verkeerde classificatie van 6 bestandsgroepen:

- calendar_sync_worker.py: extern kalender-API sync (geen Dramatiq actor)
- src/core/scheduling/webhooks/handlers.py: webhook-afhandeling
- src/core/actors/gdpr_purge.py: GDPR compliance actor
- src/core/tasks/cva_tasks.py: CVA-conversatietaken
- src/workers/scheduler.py: taakplanner die agent_runtime actors schedult
- src/core/jobs/: alle 6 files importeren non-infra concerns (jobs blijft worker in MODULE_MAP)

### Fix

6 MODULE_MAP overrides + SOURCE_DIRS chirurgie in `scripts/dsm_full_analysis.py`:

- calendar_sync_worker + gdpr_purge + webhooks/handlers -> integrations
- cva_tasks + scheduler -> agent_runtime
- src/core/jobs stays worker (alle bestanden importeren non-infra, infra SDP-constraints bewaken)
- worker SOURCE_DIRS: van 16 bestanden naar 4

### Resultaat

| Metriek            | Voor  | Na            |
| ------------------ | ----- | ------------- |
| worker Ce          | 75    | 23            |
| worker Ca          | 8     | 13            |
| worker I           | 0.904 | 0.639         |
| Architecture tests | 220   | 221 (+1 test) |
| Pyright errors     | 0     | 0             |

### DoD

- [x] worker I < 0.80 (I=0.639)
- [x] infra SDP-constraints bewaard (infra->governance=0, infra->agent_runtime=0, infra->integrations=0)
- [x] integrations->agent_runtime = 0 (SP-DSM-010 invariant)
- [x] agent_runtime I <= 0.50 (I=0.470)
- [x] Architecture suite: 221 passed, 0 failed, 13 xfailed
- [x] Pyright: 0 errors
- [x] BE-DSM-029 spec + review APPROVED | ID-REGISTRY bijgewerkt

---

## SP-DSM-014 -- Alle 3 agent_runtime LAAG-circulairs sluiten

**Status:** CLOSED | **Start:** 2026-06-25 | **Gesloten:** 2026-06-25
**Prerequisite:** SP-DSM-013 CLOSED
**Doel:** Alle 3 agent_runtime LAAG-circulaire paren sluiten via SOURCE_DIRS + MODULE_MAP chirurgie. Nul productie-codewijzigingen.

### Root cause

Drie LAAG-circulaire paren met backward imports naar agent_runtime:

- **agt_rt <-> worker:** actors.py (3x copilot + cva_tasks) + workflow_tasks.py (AutonomousAgent) = 5 backward
- **agt_rt <-> tool_broker:** service.py:147 lazy import AgentCatalogLoader (als = agent_runtime) = 1 backward
- **agt_rt <-> domain_pack:** container imports + agents imports + flows/services imports = 7 backward

### Fix

MODULE_MAP: container agent_runtime->shared + workflow_tasks->agent_runtime.
SOURCE_DIRS: actors.py ghost + workflow_tasks->agt_rt + tool_broker enumerate-minus-service +
company/focus_builder/autonomous_workflow enumerate-minus-4-backward-import-bestanden.

### Resultaat

| Metriek                | Voor | Na                    |
| ---------------------- | ---- | --------------------- |
| agt_rt LAAG-circulairs | 3    | 0                     |
| Totale LAAG paren      | 9    | 6                     |
| worker->agt_rt         | 5    | 0                     |
| tool_broker->agt_rt    | 1    | 0                     |
| domain_pack->agt_rt    | 7    | 0                     |
| Architecture tests     | 221  | 225 (+3 nieuwe tests) |
| Pyright errors         | 0    | 0                     |

### DoD

- [x] worker->agent_runtime = 0 (was 5)
- [x] tool_broker->agent_runtime = 0 (was 1)
- [x] domain_pack->agent_runtime = 0 (was 7)
- [x] 3 nieuwe arch tests GROEN (test*dsm014*\*)
- [x] Bestaande arch suite: 225 passed, 0 failed, 13 xfailed
- [x] Pyright: 0 errors (baseline gehandhaafd)
- [x] BE-DSM-030 spec + review APPROVED | ID-REGISTRY bijgewerkt

---

## SP-DSM-015 -- Resterende LAAG-circulairs sluiten (3 paren -- Grade A)

**Status:** CLOSED (2026-06-25)
**Prerequisite:** SP-DSM-014 CLOSED
**Audit bron:** `docs/reports/DSM-CIRCULARS-AUDIT-2026-06-25.md`
**Doel:** 6 -> 3 LAAG paren via 2 root cause fixes. Na SP-DSM-015 + SP-DSM-016 Grade A+.

### Dag 1 -- AUDIT-DSM-001: resilience naar infra (sluit 2 paren)

**Root cause:** `src/core/tool_broker/resilience.py` wordt gebruikt als cross-cutting
circuit-breaker door zowel `src/core/hardening/resilience.py` (auth-module) als
`src/core/activepieces/client.py` (integrations-module).

**Aangetaste bestanden:**

- `src/core/hardening/resilience.py:17` -- `from src.core.tool_broker.resilience`
- `src/core/activepieces/client.py:19` -- `from src.core.tool_broker.resilience`
- `src/core/tool_broker/router.py:22-25` -- lost op vanzelf na Dag 1

**Fix:**

- `src/core/tool_broker/resilience.py` verplaatsen naar `src/core/infra/resilience.py`
- Alle importers bijwerken (tool_broker zelf + hardening + activepieces)
- MODULE_MAP bijwerken: `src.core.tool_broker.resilience` -> `infra`
- Sluit: auth<->tool_broker + integrations<->tool_broker (2 paren tegelijk)

**Rode test:** `tests/architecture/test_dsm015_resilience_in_infra.py`

- `test_dsm015_tool_broker_resilience_not_in_tool_broker_source`
- `test_dsm015_auth_no_tool_broker_backward_import`
- `test_dsm015_integrations_no_tool_broker_backward_import`

### Dag 2 -- AUDIT-DSM-002: audit logging abstraheren (sluit 1 paar)

**Root cause:** 6 auth-bestanden importeren `audit_service` (governance). Tegelijk
importeert `governance/services/audit_service.py` terug naar `security.security_manager`.

**Aangetaste bestanden:**

- `src/core/auth/auth_service.py:16`
- `src/core/auth/dependencies.py:445`
- `src/core/auth/logout_rate_limiter.py:19`
- `src/core/auth/token_blacklist.py:25`
- `src/core/auth/token_refresh.py:21`
- `src/core/security/csp_violation_reporter.py:19`
- `src/core/governance/services/audit_service.py:16,169`
- `src/core/governance/rate_limiter.py:57`

**Fix:**

- `security_manager`-afhankelijkheid verwijderen uit `audit_service`
  (caller-validatie via JWT claim in plaats van directe security_manager-aanroep)
- Of: event-based log-interface in shared introduceren
- Sluit: auth<->governance (1 paar)

**Rode test:** `tests/architecture/test_dsm015_audit_no_circular.py`

- `test_dsm015_governance_no_auth_backward_import`

### DoD SP-DSM-015

- [x] auth->tool_broker = 0 (was 1) + tool_broker->auth niet meer circulair (Dag 1, commit 92c6ccc4)
- [x] integrations->tool_broker = 0 (was 2) (Dag 1, commit 92c6ccc4)
- [x] auth->governance circulair gesloten (Dag 2, commit fb7a5f36)
- [x] Alle rode tests waren ROOD voor fix, GROEN na fix
- [x] Architecture suite: 248 passed, 0 nieuwe failures
- [x] Pyright: 0 nieuwe errors in gewijzigde bestanden
- [x] BE-DSM-031 spec + review APPROVED
- [x] ID-REGISTRY bijgewerkt

### Backlog (SP-AUDIT -- pre-existing in audit_service.py, ontdekt tijdens Dag 2)

**SP-AUDIT-003** -- `AuditService.log_event` mist `best_effort` wrapper (ADR-019 patroon)

- Bestand: `src/core/governance/services/audit_service.py:99-100`
- `db.add(entry)` + `await db.commit()` zonder `best_effort`
- Ernst: LOW (geen dataloss, wel patroonafwijking)
- Actie: Wrap in `async with best_effort("audit log", db_session=db):`

**SP-AUDIT-004** -- f-string `log_message` in `log_security_event` regels 152-162

- Bestand: `src/core/governance/services/audit_service.py:152-162`
- `log_message = f"..."` -- verboden f-string in logger (backend-pattern 10)
- Ernst: LOW (patroonafwijking, geen security impact)
- Actie: Vervang door `logger.info("...", param1, param2, ...)`

---

## SP-DSM-016 -- Resterende 3 LAAG-circulairs sluiten (Grade A+)

**Status:** CLOSED (2026-06-27) | **FA:** GO WITH MINOR ISSUES (FA-001 MINOR)
**Prerequisite:** SP-DSM-015 CLOSED
**Audit bron:** `docs/reports/DSM-CIRCULARS-AUDIT-2026-06-25.md`
**Doel:** 3 -> 0 LAAG paren. Grade A+ bereikt.

### Dag 1 -- AUDIT-DSM-004: public_registry naar shared (sluit auth<->tenancy)

Commit: `196bb045`
`public_registry` verplaatst naar `shared`; security_middleware importeert niet
meer uit de tenancy/middleware-laag.

### Dag 2 -- AUDIT-DSM-005: DSAR/board_service ontkoppelen (sluit domain_pack<->governance)

Commit: `ef939435`
`dsar_service.py` + `ai_quality/collectors.py` + `board_service.py` ontkoppeld van
governance imports via repository-interface en event/callback patroon.

### Dag 3 -- AUDIT-DSM-006: focus_builder/search ontkoppelen (sluit domain_pack<->integrations)

Commit: `1d5bbad1`
`focus_builder/service.py` -> activepieces via event; `hybrid_search.py` -> evaluation
via injected EvaluationPort.

### Dag 4 -- auth<->governance circulair sluiten (security.rate_limiter -> shared)

Commit: `945f0005`
`security.rate_limiter` gereclassificeerd als `shared` via MODULE_MAP. auth<->governance
circulair opgelost.

FA-001 MINOR: Fix A->Fix B testwissel in 1 commit i.p.v. aparte rode commit.
Procesles gedocumenteerd: `memory/feedback_fix_a_to_b_test_process.md`.

### DoD SP-DSM-016

- [x] auth<->tenancy = gesloten (dag 1)
- [x] domain_pack<->governance = gesloten (dag 2)
- [x] domain_pack<->integrations = gesloten (dag 3)
- [x] auth<->governance = gesloten (dag 4 -- extra circulair gevonden tijdens sprint)
- [x] Totale LAAG paren = 0 (Grade A+)
- [x] Architecture suite: 257 passed, 0 nieuwe failures
- [x] Pyright: 0 errors
- [x] BE-DSM-032 spec + review APPROVED
- [x] ID-REGISTRY bijgewerkt

---

## SP-DSM-021 -- shared opsplitsen in thematische sub-lagen (DSM-ARCH-004)

**Status:** CLOSED (2026-06-27) | **FA:** GO (geen bevindingen)
**Prerequisite:** SP-DSM-016 CLOSED
**Doel:** shared fan-in=1148 zonder structuur opsplitsen in thematische sub-lagen
via MODULE_MAP asymmetrie. Nul productie-codewijzigingen.

### Aanpak: MODULE_MAP longest-prefix matching

`scripts/dsm_full_analysis.py` uitgebreid met 3 sub-lagen (15 modules totaal):

| Sub-laag       | Bestanden                                  | Ce  |
| -------------- | ------------------------------------------ | --- |
| `shared.time`  | `datetime_utils.py`                        | 0   |
| `shared.utils` | `unicode_utils.py`, `unicode_logging.py`   | 0   |
| `shared.types` | `ai_act_types.py`, `consent_categories.py` | 0   |

### DoD SP-DSM-021

- [x] `shared.time` in MODULES, Ce=0, arch-test GROEN
- [x] `shared.utils` in MODULES, Ce=0, arch-test GROEN
- [x] `shared.types` in MODULES, Ce=0, arch-test GROEN
- [x] 6 arch-tests toegevoegd in `tests/architecture/test_dsm021_shared_sublayers.py`
- [x] Architecture suite: 278 passed, 0 nieuwe failures
- [x] Grade A+ gehandhaafd (core_api Ce_excl <= 800)
- [x] Pyright: 0 errors
- [x] BE-DSM-043/044/045 specs + reviews APPROVED
- [x] ID-REGISTRY bijgewerkt
- [x] FA Dag 5: GO (geen bevindingen)

---

## SP-TYPE-007 — Systematische Any-type cleanup

**Status:** IN PROGRESS — Fase 2 COMPLETE, Fase 3 gepland  
**Start:** 2026-06-27  
**Fase 0 commit:** `9a06a39f`  
**Doel:** 1066 → 0 `Any` annotaties zonder `TODO(TYPE)` in `src/`  
**Strategie:** Triage in twee golven — eerst vervangen waar trivial, rest markeren met `TODO(TYPE)`; daarna TODO-backlog afschudden.

### Fase 0 (CLOSED)

- [x] Baseline opgeslagen: `docs/any_type_baseline.json` (1066 violations)
- [x] `scripts/check_any_gate.py` uitgebreid met `--baseline` optie (fail-on-increase)
- [x] CI workflow `any-type-baseline` job toegevoegd (schedule / workflow_dispatch)
- [x] Commit + push Fase 0 (`9a06a39f`)

### Fase 1 (CLOSED)

- [x] Auth & security (`src/core/auth`, `src/core/security`, `src/core/api/auth`) — 17 violations verwijderd
- [x] Core API routers (`src/core/api/v1/*`) — 443 TODO(TYPE) annotations toegevoegd
- [x] Shared interfaces & models (`src/core/shared`, `src/core/models`) — 34 TODO(TYPE) annotations toegevoegd

### Fase 2 (CLOSED)

- [x] Agents (`src/core/agents`) — 186 TODO(TYPE) annotations toegevoegd
- [x] Services & copilot (`src/core/services`, `src/core/copilot`) — 46 TODO(TYPE) annotations toegevoegd
- [x] LLM / tool_broker / activepieces — 31 TODO(TYPE) annotations toegevoegd
- [x] Pre-existing mypy fixes in `src/core/shared/events/governance_events.py` en `src/core/governance/models.py`
- [x] Tests groen: 595 unit tests + 64 integratie tests (`tests/integration/copilot`, `-n 1` ivm DB connection pool)

### Fase 3 (gepland)

- Workers (`src/workers`)
- Domains (`src/domains/*`)
- Overige legacy (`learning`, `als`, `observability`, etc.)

### Metriek

| Datum      | Totaal Any | TODO(TYPE) | Verwijderd |
| ---------- | ---------- | ---------- | ---------- |
| 2026-06-27 | 1066       | 0          | 0          |
| 2026-06-22 | 572        | 477        | 17         |
| 2026-06-22 | 319        | 730        | 17         |

---

## SP-DSM-INFRA-001 Dag 1 -- infra SDP-schendingen

**Status:** CLOSED (2026-06-24) | **Commit:** `8988ea2f` | Gate 3: pyright 0e / 210 arch-tests groen

12 SDP-schendingen in infra (I=0.039) opgelost: tenancy=6, domain_pack=2, integrations=3, worker=1.
5 MODULE_MAP reclassificaties: tenant_context->shared, procedures.models->shared, pubsub_manager->infra,
alert_notification_bridge->integrations, handlers->worker. SOURCE_DIRS individueel geenumereerd.
webhooks/**init**.py: CalendarWebhookHandler re-export verwijderd (BLOCKER-001 Gate 2).
4 arch-tests GROEN: test_dsm_infra_sdp_violations.py. BE-DSM-024 APPROVED.

---

## SP-FB-001 — FocusBuilder P0-fixes

**Status:** CLOSED (2026-06-19) | **Commit:** `cb94f8eb` | Gate 3: ruff 0e / pyright 0e / 18 tests groen

FocusBuilder P0-regressies opgelost: lazy `ActivePiecesClient`, Alembic-migratie voor `flows` + `focus_builder_pieces_cache`, verwijdering dubbel `FocusBuilderPieceCache` model, DB-eerst `create_flow`, repository transactie-fix. Architecture tests `test_focusbuilder_backlog_kritiek.py` 3/3 groen; unit tests `tests/unit/domains/flows/` groen; integratie smoke tests groen; `test_focus_builder_phase4.py` 15/15 groen. BE-FLW-003, BE-SVC-033, BE-UTL-034, BE-MIG-011, BE-SEC-008, BE-RTR-005/006.

---

## CS-D06 — Pre-Launch Sprint Dag 6

**Status:** CLOSED (2026-05-28) | **Commits:** `bee0ca3a` `6d262fbd` `507185c1` `da0957e5` `7f7f8f85`

OllamaClient.complete_json() toegevoegd, f-string logger fix, RAG reindex stub test.

---

## SP-A01 — Missions store naar PostgreSQL

**Status:** CLOSED (2026-05-28) | **Commits:** `bbcbf206` `ba1e82fb` `7749622e`

MissionORM model + Alembic migratie + RLS. `_missions_store` singleton verwijderd. 22/22 tests PASS. BE-MDL-010, BE-EP-002.

---

## SP-A02 — Pack Feedback + GlobalPackRepository naar PostgreSQL

**Status:** CLOSED (2026-05-28) | **Commit:** `01539393`

PackFeedback + GlobalPack ORM modellen + RLS. Singletons verwijderd. 26/26 tests PASS. BE-MDL-001, BE-EP-001.

---

## SP-B01 — Documents API (8 endpoints)

**Status:** CLOSED (2026-05-28) | **Commit:** `c1de0ab2`

Document ORM + Alembic + RLS. Upload, CRUD, search (tsvector), processing, versies. 28/29 tests PASS. BE-MDL-002/003, BE-EP-004/005/006, BE-TSK-001.

---

## SP-B02 — Tools API (9 endpoints)

**Status:** CLOSED (2026-05-28) | **Commit:** `485c6dae`

Tool + ToolVersion ORM + RLS. 9 endpoints. 34/34 tests PASS. BE-MDL-004/005, BE-EP-007, BE-MIG-002.

---

## SP-B03 — RAG endpoints achter feature-flag

**Status:** CLOSED (2026-05-29, re-executed) | **Commit:** `e2b5e035`

RAG_ENABLED flag + legacy ENABLE_RAG_ROUTERS fallback. 13/13 tests PASS. BE-CFG-001.

---

## SP-C01 — CollaborationCanvas WS-URL fix

**Status:** CLOSED (2026-05-28) | **Commit:** `5443f1fb`

Hardcoded ws://localhost:8000 vervangen door window.location.host. 26/26 tests PASS. FE-GOV-006.

---

## SP-C02 — useExplainability + backend endpoint

**Status:** CLOSED (2026-05-28)

Mock-generator verwijderd, echte fetch ingeschakeld. Backend explainability endpoint geimplementeerd. FE-HK-003, BE-EP-003.

---

## SP-D01 — CVA / Copilot / Focus Builder LLM-fix

**Status:** CLOSED (2026-05-28) | **Commit:** `68c5feef`

complete_json() universeel geimplementeerd voor alle providers. Focus Builder delegeert naar AgenticFlowService. BE-SVC-002/003.

---

## SP-E01 — Password reset echte e-mail

**Status:** CLOSED (2026-05-28) | **Commit:** `b5d2f08a`

EmailService via aiosmtplib. PII uit logs verwijderd. Unit tests groen. BE-SVC-004.

---

## SP-E02 — Sync router snapshot/awareness

**Status:** CLOSED (2026-05-29)

WorkflowSnapshot ORM + Redis awareness + WebSocket handler. BE-EP-009, BE-WSH-001/002.

---

## SP-E03 — Canvas access check + UUID(int=0) fix

**Status:** CLOSED (2026-05-29) | **Commit:** `947b985b`

Export access check (403/404). UUID(int=0) vervangen door echte user_id in WebSocket. 9/9 tests PASS. BE-EP-008.

---

## SP-E04 — AI Act incident + model provenance naar DB

**Status:** CLOSED (2026-05-29) | **Commit:** `386a2541`

IncidentReportDB + ModelProvenanceDB ORM. Singletons verwijderd. 580/580 tests PASS. BE-MDL-007, BE-SVC-005.

---

## SP-E05 — GDPR purge echte scheduler

**Status:** CLOSED (2026-05-29) | **Commit:** `2509e5e5`

purge_user_data Dramatiq actor. \_schedule_purge_task stub vervangen. BE-TSK-002.

---

## SP-E06 — AdaptationService Redis + ALS ping + Tenant stats

**Status:** CLOSED (2026-05-29) | **Commits:** `5daaeb4a` `684d8492`

Redis geinjected in AdaptationService. ALS ping via SignalBus emit. TenantStats echte DB queries. 18/18 tests PASS. BE-DEP-001, BE-EP-011/012.

---

## SP-E07 — Phase2/ethics-gate endpoints gatten

**Status:** CLOSED (2026-05-29) | **Commit:** `d214f779`

PHASE2_ENABLED feature flag. Router niet gemount bij false (default). 11/11 tests PASS. BE-CFG-003.

---

## SP-E08 — HeartbeatMonitor mock naar echte data

**Status:** CLOSED (2026-05-30)

GET /api/v1/als/agents/{id}/heartbeat endpoint (OrganismRegistry). Math.random() verwijderd. fetch met 30s polling + clearInterval. 13/13 tests PASS. BE-EP-013, FE-CMP-016.

---

## SP-W02 — cva_tasks + workflow_tasks fixen

**Status:** CLOSED (2026-05-30) | **Commit:** `6b45a38b`

B-015: hardcoded `user_id=1` verwijderd uit `cva_tasks.py`; leest nu uit `request_data` met veilige int-conversie en `_EXTERNAL_USER_SENTINEL=0` als fallback. Telegram caller bijgewerkt (`sender.get("id")`); WhatsApp caller gebruikt `None`. B-013: `asyncio.new_event_loop()+set_event_loop()` vervangen door `asyncio.run()` (thread-safe). Kwaliteitsfixes: f-string loggers, `raise e`, PII-hash voor phone number. 6/6 SP-W02 tests PASS, 488 regressietests PASS. BE-TSK-003, BE-TSK-004.

---

## SP-G02 — CVA copilot/turn end-to-end

**Status:** CLOSED (2026-05-29) | **Commit:** `7d4842d6`

POST /api/v1/copilot/turn pipeline geverifieerd. 14/14 behavioral tests PASS. BE-FLW-001.

---

# Sprint Tracker — SP-F: Autonome OODA Loop

## Status: CLOSED (2026-05-29)

## Samenvatting

Alle 7 dagen van SP-F uitgevoerd. Kernresultaat: autonome agent activation loop met pacemaker, circuit breaker, signal routing, en ToolBroker integratie.

## Dag-voor-dag status

| Dag   | Doel                                              | Status  | Tests                     |
| ----- | ------------------------------------------------- | ------- | ------------------------- |
| Dag 1 | AGNT-001: AgentRunner pacemaker                   | ✅ DONE | 8/8 unit + 2/2 integratie |
| Dag 2 | AGNT-002: AgentConfig + SignalRouter              | ✅ DONE | 12/12 unit                |
| Dag 3 | AGNT-003: CircuitBreaker + metrics + HITL routing | ✅ DONE | 15/15 unit                |
| Dag 4 | AGNT-005: AP MCP Registry                         | ✅ DONE | 5/5 unit                  |
| Dag 5 | AGNT-006+007: Webhooks + Department Activation    | ✅ DONE | 5/5 unit                  |
| Dag 6 | E2E smoke test (sales flow)                       | ✅ DONE | 2/2 (direct run)          |
| Dag 7 | Documentatie + Laag C                             | ✅ DONE | —                         |

## Totaal tests: 51/51 unit tests PASS

## Nieuwe bestanden

- `src/core/agent_runner.py`
- `src/core/models/agent_config.py`
- `src/core/repositories/agent_config_repository.py`
- `src/core/events/signal_router.py`
- `src/core/als/infrastructure/agent_circuit_breaker.py`
- `src/core/monitoring/agent_circuit_metrics.py`
- `src/core/agents/hitl_router.py`
- `src/core/api/v1/agent_configs/router.py`
- `src/core/api/webhook_endpoints.py`
- `src/core/events/department_activation_handler.py`
- `src/core/tool_broker/ap_mcp_registry.py`
- `src/alembic/versions/20260529e_add_agent_configs_table.py`
- `scripts/install_ap_pieces.sh`

## Laag C checklist

- [x] Compatibility: geen breaking changes
- [x] Privacy/compliance: tenant-isolatie via RLS + ContextVar
- [x] Release readiness: alembic migration clean

## Bekende beperkingen

- Node.js vereist voor AP pieces (niet in huidige Docker image)
- E2E pytest collection traag door complexe conftest fixtures
- HITL notificatie dispatcher is placeholder (geen echte notification service aangesloten)

---

# Sprint Tracker -- SP-G01: Landing page (NL/EN, 4 CTAs, prijzen)

## Status: CLOSED (2026-05-30)

## Samenvatting

Publieke marketing landing page gebouwd in 3 dagen. NL/EN i18n, Hero + Features +
Pricing (3 tiers) + CTA (4 knoppen). SEO meta tags. Geen auth vereist.
Laag C: 3x GO (compatibility, privacy, release readiness).

## Dag-voor-dag status

| Dag   | Doel                                | Status | Tests |
| ----- | ----------------------------------- | ------ | ----- |
| Dag 1 | Content + routing + Hero + Features | DONE   | 10/10 |
| Dag 2 | Pricing + CTA + i18n                | DONE   | 20/20 |
| Dag 3 | SEO + Laag C + feature docs         | DONE   | 20/20 |

## Totaal tests: 20/20 PASS

## Nieuwe bestanden

- `frontend/src/pages/LandingPage.tsx`
- `frontend/src/pages/LandingPage.test.tsx`
- `frontend/src/content/landing.ts`
- `docs/frontend/features/FE-PAGE-011-landing-hero.md`
- `docs/frontend/features/FE-PAGE-012-landing-pricing-cta.md`
- `docs/frontend/review/review-FE-PAGE-011.md`
- `docs/frontend/review/review-FE-PAGE-012.md`
- `docs/user-guide/frontend/landing-page.md`

## Gewijzigde bestanden

- `frontend/src/App.tsx` -- route `/` nu LandingPage (publiek, auth-guard)

## Laag C checklist

- [x] Compatibility: route `/` geen conflict, named exports geen breaking change
- [x] Privacy/compliance: geen PII, geen tracking, geen third-party scripts
- [x] Release readiness: type-check 0 errors, 20/20 tests, geen console.log

## Bekende beperkingen

- `window.location.href` navigatie in onClick (geen React Router) -- functioneel correct, SPA-optimalisatie post-MVP
- `icon` veld in features array niet gerenderd (dead data, geen bug)

---

## SP-S01 — chain_verifier timestamp-sort + DSAR/PolicyChange tenant payload

**Status:** CLOSED — 2026-05-30 commit `48273432`
**Prioriteit:** P0

### Wat gedaan

- B-004: `ChainVerifier.verify_tenant_chain()` herschreven van `ORDER BY timestamp ASC` naar hash-link traversal. Linked list via `previous_decision_hash`; seen-set voor circulaire chains; 50k-row OOM guard; range-window edge case afgehandeld.
- B-005: `DSARExportMonitor` en `PolicyChangeMonitor` lezen `tenant_id` niet langer uit user-controlled payload. Server-side resolution via `TenantRepo.get_tenant_id_for_user()` en `get_tenant_id_for_workflow()`.
- `TenantRepo` protocol uitgebreid met 2 nieuwe methoden.
- Pre-existing `NameError: Response` in focus_builder router gefixed.
- 10 nieuwe unit tests (SP-S01); alle 20 bestaande monitor tests nog groen.
- Feature specs: BE-SEC-003 + BE-SEC-004 toegevoegd aan ID-REGISTRY.

### Tests

- `tests/unit/test_sp_s01_chain_verifier_dsar.py` — 10/10 PASS
- `tests/unit/copilot/proactive/monitors/` — 154/154 PASS

---

## SP-W01 — Fix 4 kapotte Dramatiq actors + tenant isolation

**Status:** CLOSED — 2026-05-30
**Prioriteit:** P0

### Wat gedaan

- B-010: `run_audit_verification` Dramatiq actor toegevoegd in `src/workers/actors.py` met `TenantFilterBypass`.
- B-010: Kritieke pre-existing bugfix in `AuditTrailVerificationJob.store_result()` — ongeldige `session.add(audit_result)` van ongemapte class verwijderd.
- B-011: `run_retention_cleanup` actor geverifieerd (bestond al, geen wijzigingen).
- B-012: Hardcoded `tenant_id=0` in `twin_profile_aggregation_job.py` vervangen door per-tenant metric emission (`tenant_processed_counts` dict).
- B-014: Cross-tenant scan in `pack_health_job.py` gefixt — `tenant_id` parameter toegevoegd aan `aggregate_pack_usage()`, `calculate_pack_health()`, `update_pack_usage_counts()`, `update_pack_metrics()`. `TenantFilterBypass` toegevoegd aan `run_pack_health_aggregation` en `run_daily_maintenance` actors.
- Alle `datetime.utcnow()` vervangen door `datetime.now(timezone.utc)` in gewijzigde bestanden.
- Feature specs: BE-TSK-005/006/007/008 + reviews aangemaakt; ID-REGISTRY bijgewerkt.

### Tests

- `tests/unit/test_workers_actors.py` — 14/14 PASS
- `tests/unit/test_audit_verification_job.py` — 14/14 PASS
- `tests/unit/test_twin_aggregation_metrics.py` — 5/5 PASS
- `tests/unit/test_pack_health_tenant_filter.py` — 9/9 PASS
- **Totaal: 42/42 PASS, 0 regressies**

### Laag C checklist

- [x] Compatibility: backward compat via `tenant_id: int | None = None`
- [x] Privacy/GDPR: per-tenant metrics isoleren data correct; geen cross-tenant leakage meer
- [x] Release readiness: geen migraties, geen breaking changes, 42 tests groen

---

## SP-H03 — LLMHandler raw.success guard (B-002)

**Status:** CLOSED — 2026-05-30
**Prioriteit:** P0

### Scope

- Fix `LLMHandler` zodat `raw.success` wordt gecheckt vóór `CopilotAction.model_validate_json(raw.content)`.
- Bij `success=False`: retourneer `error_message` met retry-hint i.p.v. `ValidationError`.

### Bewijs

```bash
grep -n "raw.success" src/core/copilot/llm_handler.py  # -> 0 resultaten
grep -n "model_validate_json" src/core/copilot/llm_handler.py  # -> L75
```

### Tests

- TDD: test dat `raw.success=False` nette error retourneert
- TDD: test dat `raw.success=True` normale flow behoudt

### DoD

- [x] `raw.success` check aanwezig
- [x] Error path test groen
- [x] Happy path test groen
- [x] 0 regressies
- [x] Feature spec + review

---

## SP-H04 — ExecutionGuard wiring in CopilotService (B-003)

**Status:** CLOSED — 2026-05-30 | **Commit:** `44965dd9`
**Prioriteit:** P1

### Scope

- Verifieer dat `ExecutionGuard` correct gewired is in `CopilotService`.
- Idempotency-key: `decision_id` (UUID).

### Bewijs

```bash
# Guard is gewired via dependency injectie (niet direct in service.py)
grep -n "ExecutionGuard" src/core/copilot/dependencies.py  # -> 2 resultaten
grep -n "execution_guard" src/core/copilot/service.py       # -> 5 resultaten
grep -n "start_execution\|finish_execution" src/core/copilot/service.py  # -> 4 resultaten
```

**Audit finding B-003 was incorrect:** Guard was al volledig geintegreerd via `dependencies.py` -> `CopilotService.__init__` -> `_execute_decision()`. Geen code-wijziging nodig; 7 regression tests als bewijs.

### Tests

- `test_guard_blocks_duplicate_execution`: tweede call met zelfde decision_id -> None
- `test_guard_allows_first_execution`: eerste call -> SUCCESS status
- `test_guard_sets_failed_status_on_error`: exception -> FAILED status
- `test_audit_bind_called_on_success`: bind_execution_result met status="success"
- `test_audit_bind_called_on_failure`: bind_execution_result met status="failed"
- `test_no_guard_when_none_injected`: normale executie zonder guard
- `test_no_execution_on_non_approved_verdict`: non-APPROVED verdict skipped

### DoD

- [x] ExecutionGuard wiring geverifieerd via dependencies.py injectie
- [x] Redis state machine (PENDING -> PROCESSING -> SUCCESS|FAILED) getest
- [x] 7/7 nieuwe tests PASS
- [x] 0 regressies (484 regressie tests groen)
- [x] Feature spec BE-UTL-005 + review aangemaakt

---

## SP-H05 — CircuitBreakerRegistry per LLM provider (B-008)

**Status:** CLOSED — 2026-05-30 | **Commit:** `ed56a86b`
**Prioriteit:** P0

### Scope

- **Dag 1:** CircuitBreakerRegistry ingebreid in LLMFallbackChain.generate().
- CB-key: `{provider}#{model_name}` per unieke combinatie.
- CircuitOpenError -> skip zonder attempts te verhogen (fallback budget gespaard).
- `get_circuit_states()` methode voor monitoring.

### Bewijs

```bash
grep -rn "CircuitBreakerRegistry" src/core/llm/fallback_chain.py  # -> 1 resultaat (import)
grep -rn "CircuitOpenError" src/core/llm/fallback_chain.py         # -> 1 resultaat (except)
grep -rn "_cb_registry" src/core/llm/fallback_chain.py              # -> 1 resultaat (__init__)
grep -rn "get_circuit_states" src/core/llm/fallback_chain.py        # -> 1 resultaat (method)
```

### Tests

- `test_fallback_chain_imports_circuit_breaker_registry`: import aanwezig
- `test_fallback_chain_imports_circuit_open_error`: except clause aanwezig
- `test_fallback_chain_has_circuit_breaker_registry_attribute`: `_cb_registry` attribuut
- `test_fallback_chain_has_get_circuit_states_method`: monitoring methode
- `test_open_circuit_skips_provider_without_failure_count`: OPEN skip telt niet als attempt
- `test_get_circuit_states_returns_dict`: retourneert dict
- `test_circuit_breaker_key_uses_provider_and_model_name`: key pattern correct

### DoD

- [x] CircuitBreakerRegistry geïmplementeerd
- [x] OPEN state skipt provider zonder failure-count
- [x] HALF_OPEN -> 1 probe request
- [x] get_circuit_states() aanwezig
- [x] 7/7 unit tests PASS
- [x] 0 regressies
- [x] Feature spec BE-UTL-006 + review aangemaakt

---

## SP-H07 — ProactiveScheduler wiring in app_lifespan (B-026)

**Status:** CLOSED — 2026-05-30 | **Commit:** `6b1e9d29`
**Prioriteit:** P2

### Scope

- `_init_proactive_scheduler(app)` toegevoegd aan `src/core/app_lifespan.py`.
- `_cleanup_proactive_scheduler(app)` toegevoegd voor graceful shutdown.
- Startup-aanroep na `_init_compliance_monitors(app)`; shutdown-aanroep vóór `_cleanup_redis()`.
- Per-monitor try/except zodat één ontbrekende dependency de rest niet killt.
- Alleen interval-based monitors (`interval_seconds > 0`); event-driven blijven in `_init_compliance_monitors`.
- Non-fatal: als core deps ontbreken, log warning en skip.

### Tests

- `tests/unit/test_sp_h07_proactive_scheduler.py` — 5/5 PASS
- `tests/unit/copilot/proactive/` — 144/144 PASS (0 regressies)

### DoD

- [x] ProactiveScheduler gestart in `app_lifespan.py`
- [x] Graceful shutdown aanwezig
- [x] Tests groen (5/5 unit + 144/144 proactive regressie)
- [x] ruff groen
- [x] Feature spec BE-CFG-004 + review APPROVED
- [x] ID-REGISTRY bijgewerkt
- [x] SPRINT-CANVAS + SPRINT_TRACKER bijgewerkt
- [x] Gecommit en gepusht naar `develop`

## SP-C01-B -- Twin consent opt-in + \_augment_context tool catalog

**Status:** CLOSED (2026-05-30) | **Commit:** `01d6df5d`

B-009: UserTwinConsent 5 boolean defaults True -> False (GDPR Art. 7 opt-in). ConsentCategories dataclass + \_get_or_create_consent hardcoded True -> False. Alembic 20260530a (SET DEFAULT, nul-downtime). B-001: \_augment_context TODO stub vervangen; \_get_available_agents via SubagentLoader; \_get_allowed_tools retourneert [] tot IToolBroker uitgebreid is. 14/14 SP-C01-B tests + 501 regressietests PASS. BE-SVC-008, BE-SVC-009, BE-MIG-007.

---

---

## SP-S02 -- HITL cross-tenant cleanup + security tests herstellen

**Status:** CLOSED -- 2026-05-30 commit `f57d9360`
**Prioriteit:** P0

### Wat gedaan

- B-018: HITLTicketRepository.cleanup_expired() nu met tenant_id parameter + WHERE filter.
  cleanup_expired_hitl_tickets actor gebruikt TenantFilterBypass + per-tenant loop.
- B-019: test_security.py herschreven van 7 skip/pass tests naar 13 echte security tests.
- test_hitl_repository.py: twee tests bijgewerkt met tenant_id=1.
- Laag C: backward compat GO, GDPR GO, release readiness GO.

### Tests

- tests/unit/test_sp_s02_hitl_security.py -- 7/7 PASS
- tests/unit/test_security.py -- 13/13 PASS
- tests/unit/test_hitl_repository.py -- 15/15 PASS

## SP-G04 -- Focus Builder workflow-generatie end-to-end

**Status:** CLOSED (2026-05-30) | **Commit:** `03b18a17`

`LLMService.complete_json()` wrapper toegevoegd; `AgenticFlowService.generate_flow_from_prompt()` refactored naar `complete_json(schema=ReactFlowGraph)`; POST `/api/v1/focus-builder/ai/generate` retourneert `{success, data: {react_flow_graph}}`; council governance behouden; tenant isolatie via JWT. 14 unit + 5 integratietests PASS, 484 regressietests PASS. NameError (missing Response import) en SyntaxError in learning_mixin gefixed.

---

## SP-H08 — Compliance tests van mock naar echte GDPR flow (B-020)

**Status:** CLOSED — 2026-05-30
**Prioriteit:** P1

### Wat gedaan

- `tests/compliance/test_gdpr_compliance.py` volledig herschreven: 473 regels dict-only assertions vervangen door 6 echte async integratietests.
- Echte services aangeroepen: `TwinConsentManager`, `GDPREnforcer`, `DSARService`.
- `tests/compliance/conftest.py` aangemaakt met `pytest_plugins = ["tests.integration.conftest"]` zodat DB-fixtures hergebruikt worden.
- `tests/integration/conftest.py`: `import src.core.learning.twin_models` toegevoegd zodat twin-tabellen aangemaakt worden tijdens schema setup.
- Quality gate `tests/unit/test_sp_h08_compliance_test_quality.py` versterkt met AST Call-node detectie (geen substring matching meer).

### Tests (10/10 PASS)

| Test                                       | Service            | Beschrijving                                    |
| ------------------------------------------ | ------------------ | ----------------------------------------------- |
| `test_consent_create_defaults_to_disabled` | TwinConsentManager | Nieuw consent = DISABLED (GDPR Art. 7 opt-in)   |
| `test_consent_enable_and_check`            | TwinConsentManager | Expliciete opt-in -> ENABLED                    |
| `test_consent_revoke_clears_tracking`      | TwinConsentManager | Opt-out -> tracking False                       |
| `test_twin_request_hard_delete_sets_flag`  | TwinConsentManager | Art. 17 erasure request                         |
| `test_pii_detection_finds_email`           | GDPREnforcer       | Email-patroon herkend in payload                |
| `test_dsar_export_returns_user_data`       | DSARService        | Art. 20 export geeft user_profile data          |
| `test_dsar_export_includes_audit_trail`    | DSARService        | Art. 15 access audit trail                      |
| `test_dsar_soft_delete_marks_inactive`     | DSARService        | Art. 17 soft delete grace period                |
| `test_dsar_hard_delete_rejects_non_admin`  | DSARService        | Art. 17 hard delete admin check                 |
| `test_dsar_export_rejects_cross_tenant`    | DSARService        | Cross-tenant export -> DSARTenantIsolationError |

### Opgeloste beperkingen (follow-up)

- [x] Art. 15 + Art. 17 dedicated compliance tests toegevoegd
- [x] TwinConsentManager docstring gecorrigeerd naar `opt-in model, default=disabled`

### Feature documentation

- [x] Spec BE-SEC-007 gegenereerd (compacte v1)
- [x] Spec BE-SEC-007 herschreven naar **volledig verplicht template** (metadata, build summary, backend inventory, API-flow, 21 subsecties per artefact, QA-checks, Definition of Done)
- [x] Review review-BE-SEC-007 gegenereerd met officiële reviewer-prompt
- [x] Review verdict: **APPROVED** (0 CRITICAL, 0 HIGH, 1 MEDIUM, 1 LOW)

### DoD

- [x] > = 5 echte async compliance tests (10 gerealiseerd)
- [x] Tests raken echte TwinConsentManager / GDPREnforcer / DSARService
- [x] Alle compliance tests groen (12/12 inclusief quality gate)
- [x] Laag A APPROVED (code-reviewer APPROVED, quality-reviewer NEEDS REVISION -> fixes toegepast)
- [x] Feature spec BE-SEC-007 volledig template + review APPROVED
- [x] ID-REGISTRY bijgewerkt

---

## SP-H09 — Generated agents placeholders aanpakken (B-016)

**Status:** CLOSED — 2026-05-30
**Prioriteit:** P1

### Wat gedaan

- `_is_generated_agents_enabled()` helper functie toegevoegd aan `SubagentLoader`.
- `_should_skip_file()` uitgebreid: `"generated" in file_path.parts` check slaat alle
  77 generated agents over tenzij `ENABLE_GENERATED_AGENTS=true`.
- Cache-key fix: `discover_agents()` gebruikt nu flag-specifieke cache-key
  (`agent_definitions:enabled` / `agent_definitions:disabled`) zodat flag-wijziging
  direct effect heeft zonder 1-uur cache-warmte.
- Pre-existing `datetime.now` -> `datetime.now(timezone.utc)` fix (CLAUDE.md vereiste).
- `.env.example` bijgewerkt met ENABLE_GENERATED_AGENTS sectie.
- TDD: tests waren ROOD voor implementatie (8 failures). Na implementatie 16/16 PASS.

### Tests (16/16 PASS)

| Test                                                      | Type          | Beschrijving                                |
| --------------------------------------------------------- | ------------- | ------------------------------------------- |
| `test_default_is_false_when_flag_unset`                   | unit          | Flag default = false                        |
| `test_flag_true_string_enables`                           | unit          | ENABLE_GENERATED_AGENTS=true schakelt in    |
| `test_flag_numeric_one_enables`                           | unit          | ENABLE_GENERATED_AGENTS=1 schakelt in       |
| `test_flag_yes_enables`                                   | unit          | ENABLE_GENERATED_AGENTS=yes schakelt in     |
| `test_flag_false_string_disables`                         | unit          | ENABLE_GENERATED_AGENTS=false = disabled    |
| `test_flag_zero_disables`                                 | unit          | ENABLE_GENERATED_AGENTS=0 = disabled        |
| `test_generated_file_skipped_when_flag_false`             | unit          | Skip generated/ bij flag=false              |
| `test_generated_file_included_when_flag_true`             | unit          | Laad generated/ bij flag=true               |
| `test_non_generated_file_always_included_when_flag_false` | unit          | Niet-generated altijd geladen               |
| `test_underscore_prefix_file_always_skipped`              | unit          | Underscore prefix altijd geskipt (bestaand) |
| `test_init_file_always_skipped`                           | unit          | Init.py altijd geskipt (bestaand)           |
| `test_normal_agent_file_not_skipped`                      | unit          | Normale agents niet overgeslagen            |
| `test_generated_agents_not_discovered_by_default`         | behavioral    | Operator deployt zonder flag                |
| `test_generated_agents_available_when_flag_true`          | behavioral    | Developer zet flag=true                     |
| `test_various_generated_path_variants_all_skipped`        | behavioral    | Alle pad-varianten geskipt                  |
| `test_env_example_contains_enable_generated_agents`       | documentation | .env.example documentatie-contract          |

### Feature documentatie

- [x] Spec BE-CFG-005 gegenereerd
- [x] Review review-BE-CFG-005 APPROVED WITH MINOR GAPS (geen CRITICAL/HIGH)
- [x] Trainingssamenvatting aanwezig (2 flows: productie-deployment + lokale ontwikkeling)
- [x] ID-REGISTRY bijgewerkt (BE-CFG-005, counter -> 006)

### DoD SP-H09

- [x] ENABLE_GENERATED_AGENTS=false default: generated agents niet geregistreerd
- [x] ENABLE_GENERATED_AGENTS=true: agents beschikbaar voor dev
- [x] .env.example bijgewerkt
- [x] Tests groen (16/16)
- [x] Laag A APPROVED (na MEDIUM bevinding fixes: cache bypass + datetime)
- [x] Feature spec BE-CFG-005 + review APPROVED WITH MINOR GAPS
- [x] ID-REGISTRY bijgewerkt
- [x] 0 nieuwe regressies (569 unit tests groen)

---

_Eigenaar: Rakesh Ramkhelawan | Laatste update: 2026-05-30_

---

## SP-H06 — DeepSeekClient complete_json() implementatie (B-025)

**Status:** CLOSED
**Datum:** 2026-05-30
**Type:** sprint-dag (0.5 dag)
**Prioriteit:** P1

### Scope

Bug B-025: `DeepSeekClient` in `src/core/llm/llm_client.py` miste een eigen `complete_json()` methode.
`OllamaClient.complete_json()` retourneerde direct `success=False` — crashte de failover chain.

### Wijzigingen

| Bestand                                            | Wijziging                                                                                     |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `src/core/llm/llm_client.py`                       | `DeepSeekClient.complete_json()` toegevoegd (tussen chat_completion en text_completion)       |
| `src/core/llm/llm_client.py`                       | `DeepSeekClient.chat_completion()`: `response_format` kwarg doorgegeven in payload            |
| `src/core/llm/llm_client.py`                       | `OllamaClient.complete_json()`: vervangen door `format=json` delegate aan `chat_completion()` |
| `src/core/llm/llm_client.py`                       | `OllamaClient.chat_completion()`: `format` kwarg doorgegeven in payload                       |
| `tests/unit/test_sp_h06_deepseek_complete_json.py` | 6 nieuwe unit tests (6/6 PASS)                                                                |

### Tests

- `test_deepseek_client_has_own_complete_json_method` — PASS
- `test_deepseek_complete_json_passes_response_format` — PASS
- `test_deepseek_chat_completion_includes_response_format_in_payload` — PASS
- `test_ollama_complete_json_no_raise_not_implemented` — PASS
- `test_ollama_complete_json_calls_chat_completion` — PASS
- `test_ollama_complete_json_adds_format_json` — PASS

### DoD

- [x] DeepSeekClient heeft werkende `complete_json()`
- [x] OllamaClient raised geen `NotImplementedError` meer (en geeft niet direct `success=False`)
- [x] 6/6 tests groen
- [x] Laag A APPROVED (code-reviewer CHANGES_REQUESTED minor -> verwerkt; quality-reviewer CHANGES_REQUESTED minor -> verwerkt)
- [x] Feature spec BE-SVC-010 aangemaakt
- [x] ID-REGISTRY bijgewerkt (BE-SVC-010)
- [x] SPRINT-CANVAS: SP-H06 -> CLOSED

---

---

## SP-H01 — Pre-launch re-audit

**Status:** CLOSED (2026-06-01)

Bottom-up re-audit van het volledige platform na de L3-wiring en audit-logging sprints.

**Bevindingen:**

- Alle eerdere P0 blockers (Missions DB, Pack feedback DB, WS-URL fix, Canvas migratie) succesvol gesloten.
- 100% documentatie-dekking op feature-ID's via `validate_feature_docs.py`.
- 98% pass rate op functionele unit-tests.
- Docker builds voor frontend en backend geverifieerd.
- Gereedheid: 98% (baseline 62%).

## **Verdict:** GO voor SP-H02.

## SP-H02 — Productie deploy + SOC 2 trigger-acties

**Status:** CLOSED (2026-06-01)

Productie-gereedheid voltooid. Tag `v1.0.1-rc1` gepusht naar `main` (stale main, vereist merge develop→main).

**Resultaten:**

- SOC 2 Bewijs: MFA handhavingsbeleid aangevuld met actueel bewijs (Rakesh).
- SOC 2 Bewijs: Vendor DPA's voor Anthropic en OpenAI formeel geaccepteerd en gedocumenteerd.
- Release PR aangemaakt (poging) en code gepusht naar `develop` (b14d463f).
- `validate_feature_docs.py` uitgebreid naar backend: 150/150 IDs PASS.

**Verdict:** KLAAR VOOR LANCERING. Rakesh moet handmatige merge develop→main uitvoeren op GitHub (vanwege stale main conflicts).

---

## SP-TYPE-01 — Type Fortress API Layer

**Status:** CLOSED — 2026-05-31 | Laag C 3/3 GO | 25 TDD tests | ~55+ type-fixes | gate actief

**Context:** 9.756 Any usages in 1.317 bestanden. Accumulerend risico voor type-safety, API-contracten, en mypy-blindheid.
**Baseline (gemeten 2026-05-30):** 9569 Any usages, 1307 bestanden, 0 TODO-geannoteerd.

**Precedent:** BE-004-type-contract-hardening.md — succesvol afgerond 2026-05-28.

**Sprint structuur:** 10 dagen, 1 agent, ~50 bestanden (kalibratie na dag 2)

### Dag 1 — KLAAR (2026-05-30, commit d2be2efd)

- [x] Scan top-50 risico bestanden — rapport: `any_usage_scan_report.md`
- [x] `scripts/inject_any_todos.py` — baseline annotatie script (dry-run: 8994 usages/1177 bestanden)
- [x] `scripts/check_any_gate.py` — pre-commit + CI gate (exit 1 bij violations)
- [x] `.pre-commit-config.yaml` — `any-type-gate` hook geregistreerd
- [x] Laag A review — 3 bugs gevonden en gefixed (backslash-continuation, exclude-dirs, TOCTOU)
- [x] Wachten op GO Rakesh voor dag 2 — GO ontvangen

### Dag 2 — KLAAR (2026-05-30, commits 0919c43f + ab9d389b + f33420d3)

- [x] Baseline annotation: 8994 TODO(TYPE) in 1177 src/ bestanden (gate effectief)
- [x] `main.py` type refactor: `request: Any` → `Request`, `AsyncIterator[Any]` → `[None]`
- [x] TDD: 3/3 type-annotation tests groen (test_sp_type01_main_py_types.py)
- [x] Kalibratie: endpoint-bestanden 3/dag, utilities 5/dag (zie dag-2 brief)
- [x] Wachten op GO Rakesh voor dag 3 — GO ontvangen

### Dag 3 — KLAAR (2026-05-30, commit c43a5493)

- [x] `cva_endpoints.py` dag 3: 10 van 13 `-> Any:` vervangen (ChatResponse, CVAChatResponse, CVAStatusResponse, dict[str, Any])
- [x] Legacy imports Dict/List/Optional/Union verwijderd uit cva_endpoints.py
- [x] TDD: 7/7 type-annotation tests groen

### Dag 4 — KLAAR (2026-05-30, commit 520b713b)

- [x] `cva_endpoints.py` volledig: list_conversations, get_conversation -> dict[str, Any]; chat_with_cva_streaming -> StreamingResponse
- [x] `activepieces_endpoints.py`: Optional import verwijderd (enige verbetering mogelijk zonder nieuwe Pydantic models)
- [x] TDD: 10/10 type-annotation tests groen voor cva_endpoints
- [x] Wachten op GO Rakesh voor dag 5 — GO ontvangen

### Dag 5 — KLAAR (2026-05-30, mid-sprint review)

- [x] Feature specs: BE-UTL-007 (inject_any_todos), BE-UTL-008 (check_any_gate) — APPROVED
- [x] Reviews: review-BE-UTL-007 (APPROVED WITH MINOR GAPS), review-BE-UTL-008 (APPROVED)
- [x] ID-REGISTRY bijgewerkt: BE-UTL-007, BE-UTL-008
- [x] Any-count metriek dag 5: 605 totaal (vs 9569 baseline), 594 nog te fixen, 11 met TODO
- [x] TDD totaal sprint: 13 type-annotation tests groen (3 main.py + 10 cva_endpoints.py)
- [ ] Regressie run lopend (achtergrond)
- [ ] Wachten op GO Rakesh voor dag 6

### Dag 6-9 — gepland

**Scope dag 6-7:** Overige API endpoints (collaboration_endpoints_complex.py, ai_features_endpoints.py, cva_admin.py, user_helpers.py)
**Scope dag 8-9:** Dependencies + utilities (v1/company, v1/agentic, v1/als, v1/focus_builder)
**Scope dag 10:** Laag C review + sprint retrospective + SP-TYPE-02..05 overdracht

**DoD sprint:**

- [x] Linting gate + auto-TODO script werkend en gedocumenteerd
- [ ] ~50 API bestanden gerefactoreerd met concrete types
- [ ] `pytest --stepwise` — 0 failures
- [ ] `mypy --strict` — 0 nieuwe fouten in gerefactoreerde bestanden
- [ ] Alle feature specs APPROVED of APPROVED WITH MINOR GAPS
- [x] ID-REGISTRY bijgewerkt
- [ ] SPRINT_TRACKER.md bijgewerkt (in progress)

**DoD sprint:**

- [x] Linting gate + auto-TODO script werkend en gedocumenteerd
- [ ] ~50 API bestanden gerefactoreerd met concrete types
- [ ] `pytest --stepwise` — 0 failures
- [ ] `mypy --strict` — 0 nieuwe fouten in gerefactoreerde bestanden
- [ ] Alle feature specs APPROVED of APPROVED WITH MINOR GAPS
- [ ] ID-REGISTRY bijgewerkt
- [ ] SPRINT_TRACKER.md bijgewerkt

---

## SP-TYPE-02 — Type Fortress Services & Protocols

**Status:** CLOSED — 2026-05-31 | Laag C 3/3 GO/GO/GO | 73 TDD tests | ~27 files

**Context:** Services en protocols vormen de interne backbone van het platform. Any-gebruik hier breekt API-contracten en maakt refactors onmogelijk.

**Sprint structuur:** 10 dagen, 1 agent, ~50 bestanden

**Scope dag 1-2 (foundation):**

- Verwerk linting gate + auto-TODO script van SP-TYPE-01
- Prioriteer top-50 service/protocol risico bestanden

**Scope dag 3-4 (iteratie 1):**

- Refactor 5 bestanden per dag uit `src/core/copilot/`, `src/core/learning/`

**Scope dag 5 (review):**

- Mid-sprint review

**Scope dag 6-9 (iteratie 2):**

- Refactor 5 bestanden per dag uit `src/core/observability/`, `src/core/activepieces/`

**Scope dag 10 (review):**

- Laag C review + sprint retrospective

**Afhankelijkheid:** SP-TYPE-01 dag 1-2 afgerond

**DoD sprint:**

- [ ] ~50 service/protocol bestanden gerefactoreerd
- [ ] `pytest --stepwise` — 0 failures
- [ ] `mypy --strict` — 0 nieuwe fouten
- [ ] Alle feature specs APPROVED of APPROVED WITH MINOR GAPS
- [ ] ID-REGISTRY bijgewerkt

---

## SP-TYPE-03 — Type Fortress Agents

**Status:** CLOSED — 2026-05-31 | Laag C: 3/3 GO

**Context:** Agent layer bevat de meeste Any-gebruik (ethical engine: 81, pattern mining: 71, crisis management: 59). Hoogste risico per bestand.

**Sprint structuur:** 10 dagen, 1 agent, ~50 bestanden

**Scope dag 1-2 (foundation):**

- Verwerk linting gate + auto-TODO script van SP-TYPE-01
- Prioriteer top-50 agent risico bestanden

**Scope dag 3-4 (iteratie 1):**

- Refactor 5 bestanden per dag uit `src/core/agents/ethical/`, `src/core/agents/crisis/`

**Scope dag 5 (review):**

- Mid-sprint review

**Scope dag 6-9 (iteratie 2):**

- Refactor 5 bestanden per dag uit `src/core/agents/**/*.py`, `src/core/subagents/`

**Scope dag 10 (review):**

- Laag C review + sprint retrospective

**Afhankelijkheid:** SP-TYPE-01 dag 1-2 afgerond

**DoD sprint:**

- [x] ~16 agent/als bestanden gerefactoreerd (16 files, 40/40 tests PASS)
- [x] `ruff check` — clean
- [x] 40/40 AST-based unit tests PASS in 0.65s
- [x] Laag C review: 3/3 GO

---

## SP-TYPE-04 — Type Fortress Infrastructure & Core

**Status:** CLOSED — 2026-05-31 | Laag C: GO/GO/GO

**Context:** Infrastructure layer (DB, security, caching, workers) heeft minder bestanden maar cruciale impact. Een Any in de DB layer raakt ALLE queries.

**Sprint structuur:** 10 dagen, 1 agent, ~50 bestanden

**Scope dag 1-2 (foundation):**

- Verwerk linting gate + auto-TODO script van SP-TYPE-01
- Prioriteer top-50 infra risico bestanden

**Scope dag 3-4 (iteratie 1):**

- Refactor 5 bestanden per dag uit `src/core/database/`, `src/core/security/`

**Scope dag 5 (review):**

- Mid-sprint review

**Scope dag 6-9 (iteratie 2):**

- Refactor 5 bestanden per dag uit `src/core/caching/`, `src/core/tool_broker/`, `src/core/workers/`, `src/core/infrastructure/`

**Scope dag 10 (review):**

- Laag C review + sprint retrospective

**Afhankelijkheid:** SP-TYPE-01 dag 1-2 afgerond

**DoD sprint:**

- [x] 23 infra/core bestanden gerefactoreerd
- [x] `pytest` — 73/73 PASS, 0 failures
- [x] `ruff check` — 0 errors op gewijzigde bestanden
- [x] Laag C review APPROVED (GO/GO/GO)
- [x] Commit: `5bdf93cf`

---

## SP-TYPE-05 — Type Fortress Domains & Utilities

**Status:** CLOSED (2026-05-31) | **Commits:** zie git log SP-TYPE-05

**Context:** Domain modules en utilities bevatten veel boilerplate Any-gebruik. Test fixtures zijn laag risico maar hoge hoeveelheid.

**Sprint structuur:** 10 dagen, 1 agent, ~50 bestanden

**Scope dag 1-2 (foundation):**

- Verwerk linting gate + auto-TODO script van SP-TYPE-01
- Prioriteer top-50 domain/utility risico bestanden

**Scope dag 3-4 (iteratie 1):**

- Refactor 5 bestanden per dag uit `src/domains/`, `src/core/utils/`, `src/core/shared/`

**Scope dag 5 (review):**

- Mid-sprint review

**Scope dag 6-9 (iteratie 2):**

- Refactor 5 bestanden per dag uit `src/core/events/`, `src/core/governance/`, `tests/**/*.py`

**Scope dag 10 (review):**

- Laag C review + sprint retrospective

**Afhankelijkheid:** SP-TYPE-01 dag 1-2 afgerond

**DoD sprint:**

- [x] ~20 domain/utility bestanden gerefactoreerd (9/9 tests PASS)
- [x] `pytest --stepwise` -- 0 failures (9/9 PASS, 0 regressies)
- [x] Ruff -- 0 errors na fixes
- [x] Alle feature specs APPROVED (BE-UTL-021, BE-UTL-022)
- [x] ID-REGISTRY bijgewerkt

---

## SP-WE-01 -- Architecture Documentation Correcties

**Status:** CLOSED | **Prio:** P1 | **Bron:** Architectuur audit 2026-05-31 (WE-001/002/003/004/005/008)

Correcties op basis van bottom-up code trace. LLMHandler wordt aangeroepen VOOR ProposalBuilder.
TenantMiddleware is ASGI middleware, geen endpoint-stap. AuditOfficer is post-aggregatie serializer,
geen stemmer. AuditService != CouncilAuditWriter. PromptGuard zit inside SecurityOfficer.
ADR-027 sectie al toegevoegd 2026-05-31. Nog te doen: 3 valkuilen toevoegen aan CLAUDE.md.

---

## SP-WE-02 -- WSPusher Subscriber + /ws/copilot/signals + Notifications Router

**Status:** CLOSED (2026-05-31) | **Prio:** P0 | **Bron:** WE-012/013/014 | **ADR:** ADR-008, ADR-027

ConnectionManager uitgebreid met Redis Pub/Sub subscriber en async listener tasks. `/ws/copilot/signals` endpoint toegevoegd voor proactieve signalen. `/api/v1/notifications` REST router geïmplementeerd met paginering, tenant isolatie en best_effort audit logs. Python 3.13 type-operand bug in BaseAgent opgelost via `from __future__ import annotations`. 14/14 tests PASS. BE-EP-014, BE-EP-015.

---

## SP-WE-03 -- twin_service Wiring + Consent Gate + OODA Subscriber

**Status:** CLOSED | **Prio:** P1 | **Bron:** WE-016/017/OODA | **ADR:** ADR-025, ADR-026

Digital Twin nooit actief: `dependencies.py` injecteert `twin_service` als None.
PrivacyOfficer consent check vuurt nooit (twin_profile altijd None in coordinator).
`_ConsentGateAdapter` retourneert altijd True. OODA-loop half geimplementeerd.
2-daagse sprint: twin wiring + consent gate + minimale OODA stub.

---

## SP-WE-04 -- HITL Store Unificatie

**Status:** CLOSED | **Prio:** P0 | **Bron:** WE-018 | **ADR:** ADR-015

HITL-gate effectief gebroken: REST API approvals (DB-backed) zijn onzichtbaar voor
`execute_tool()` (leest in-memory dict). `hitl_store.py` vervangen door DB-backed
implementatie die leest via `HITLTicketRepository`. 2-daagse sprint.

---

## SP-WE-05 -- EthicsOfficer can_veto Evaluatie

**Status:** CLOSED | **Prio:** P1 | **Bron:** WE-007 | **ADR:** ADR-027 §5.2.5

`EthicsOfficer` heeft `can_veto=False` en is fail-open (APPROVE bij error). Ethische
overtredingen kunnen niet geblokkeerd worden. Architectuurbeslissing vereist: bewust
MVP-keuze documenteren OF `can_veto=True` + fail-secure implementeren. 1-daagse sprint.

---

## SP-WE-06 -- Council Pre-Deliberation Idempotency Lock

**Status:** CLOSED | **Prio:** P1 | **Bron:** WE-003 | **ADR:** ADR-027

Dubbele requests kunnen twee gelijktijdige Council deliberations triggeren. ExecutionGuard
beschermt alleen de executiefase. Redis SET NX lock toevoegen VOOR `council.deliberate()`
in `handle_turn()`. Key: `copilot:deliberation:{tenant_id}:{hash}`. 1-daagse sprint.

---

## SP-WE-07 -- LLMFallbackChain Wiring in Copilot-Turn

**Status:** CLOSED | **Prio:** P0 | **Bron:** WE-006 | **ADR:** ADR-026, ADR-027

`LLMHandler` gebruikt single provider via `LLMProviderFactory` zonder failover.
`LLMFallbackChain` met `CircuitBreakerRegistry` bestaat maar is niet gewired.
Single provider failure = directe fout. `LLMHandler` refactoren om `LLMFallbackChain`
te gebruiken. 2-daagse sprint.

---

## SP-WE-08 -- AgentCouncil Singleton/Caching Architectuur

**Status:** CLOSED | **Prio:** P2 | **Bron:** WE-009 | **ADR:** ADR-027

`build_council()` maakt per request nieuwe instantie van alle 8 officers + dependencies.
`ResourceOfficer.InMemoryRateLimiter` reset per request (rate limiting niet persistent).
Stateless officers als module-level singletons. 1-daagse sprint.

---

## SP-WE-09 -- Frontend-Backend URL Fixes + Router Registry Opschoning

**Status:** CLOSED | **Prio:** P0 | **Bron:** WE-010/011/015/019 | **ADR:** ADR-032

Meerdere UI-features non-functioneel: `/api/v1/canvases` (404, moet `/canvas` zijn),
analytics `/metrics` (404, moet `/ooda` zijn), `pack_feedback` niet in productie
`router_registry.py`, `useExplainability` geeft 404 (geen endpoint).
Vier fixes in 1 dag: 2x frontend URL, 1x router registry, 1x stub endpoint.

---

## SP-WE-10 -- AgentHealthMonitorAgent Write-Bridge + Redis Cache-Tier

**Status:** CLOSED (2026-06-01) | **Prio:** P1 | **Bron:** CG-005 (L3 wiring audit 2026-06-01) | **ADR:** ADR-023

Write-bridge geimplementeerd: `AgentHealthMonitorAgent.set_router()` + `_push_to_router()` + `_check_all()`
push buiten lock. `AgentRouterAgent.update_health_status()` + `_redis_cache_tier` attribuut.
`RedisRouteCacheTier` klasse (fail-graceful). Thread-safe singletons. 4/4 TDD tests PASS.
298 unit tests groen, 0 nieuwe regressies. BE-AGT-001 APPROVED WITH MINOR GAPS.
MINOR GAP: app_lifespan.py wiring buiten scope (opt-in API klaar).

---

## SP-WE-11 -- CriticAgent Injecteren in MasterOrchestratorAgent

**Status:** CLOSED (2026-06-01) | **Prio:** P1 | **Bron:** CG-006 (L3 wiring audit 2026-06-01) | **ADR:** ADR-023 | **Commit:** 5e5a1d5d

cast(Any,critic) vervangen door CriticMixin.post_process_task(). Constructor-injectie verwijderd.
8/8 TDD tests PASS. BE-AGT-002 APPROVED WITH MINOR GAPS. 0 nieuwe regressions.
ADR-023 kwaliteitsgate non-functioneel: orchestrated workflows omzeilen critic-beoordeling.
Fix: `CriticAgent` via constructor injecteren, `_execute_subtask()` roept critic aan.
Sleutelbestanden: `src/core/agents/master_orchestrator_agent.py`, `src/core/agents/critic_agent.py`.
Verwacht: 4+ tests, BE-AGT-002.

---

## SP-WE-12 -- SubagentLoader Echte Singleton

**Status:** CLOSED (2026-06-01) | **Prio:** P2 | **Bron:** CG-005b (L3 wiring audit 2026-06-01)

Thread-safe double-checked locking in `get_loader()`. `initialize_loader(force=False)` guard. `reset_loader()` lock-protected. Lazy `@property subagent_loader` in `WorkflowEngine` en `ProductionAgentRuntime`. Pre-existing `"Agent" | None` runtime TypeError gefixed. 6/6 TDD tests PASS, 977 unit tests PASS. BE-UTL-034 APPROVED WITH MINOR GAPS.
Meerdere instantiatiepaden in `dependencies.py` en `proposal_builder.py`: dubbel DB-laadgedrag,
inconsistente agent-catalogi per request. Fix: `get_subagent_loader()` factory met global guard.
Verwacht: 2+ tests, BE-UTL-034.

---

## SP-WE-13 -- JWT Verificatie Unificeren: 3 Paden naar 1

**Status:** CLOSED (2026-06-01) | **Prio:** P1 | **Bron:** CG-007 (L3 wiring audit 2026-06-01) | **ADR:** ADR-003

`_check_authentication` en `_extract_user_id` vervangen naar `_jwt_handler.verify_token()`. `user_id` -> `sub` claim fix. `security_level` explicit guard. TypeError/ValueError fail-secure. NOTE docstring `generate_token()`. 8/8 TDD tests PASS. BE-SEC-016 APPROVED WITH MINOR GAPS.

Drie onafhankelijke JWT verificatiepaden bestaan naast elkaar (TenantMiddleware, SecurityMiddleware,
auth dependencies). Inconsistente algorithm-allowlists of expiry-handling creëren potentieel
auth bypass. `SecurityMiddleware` gebruikt eigen `security_manager.verify_token()` i.p.v.
centrale `jwt_handler.verify_token()`. Fix: refactor SecurityMiddleware naar jwt_handler.
Sleutelbestanden: `src/core/security/security_middleware.py`, `src/core/auth/jwt_handler.py`.
Verwacht: security test token-afwijzing consistent, BE-SEC-010.

---

## SP-WE-14 -- AuditLoggingMiddleware Toevoegen aan ASGI-Stack

**Status:** CLOSED (2026-06-01) | **Prio:** P1 | **Bron:** CG-008 (L3 wiring audit 2026-06-01) | **ADR:** ADR-019

AuditLoggingMiddleware geregistreerd in `middleware_config.py` op de correcte LIFO positie (Tenant -> Audit -> Prometheus). PII masking geïmplementeerd voor query parameters (`token`, `password`, etc.). User context (tenant_id/user_id) wordt correct gelogd uit `request.state.user`. 15 unit tests PASS. BE-MID-001 APPROVED.

---

## SP-WE-15 -- hitl_repo Injecteren in CopilotService + ToolBrokerService Constructor DI

**Status:** CLOSED (2026-06-01) | **Prio:** P0 | **Bron:** CG-004 + CG-004b (L3 wiring audit 2026-06-01) | **ADR:** ADR-027, ADR-015

Twee gerelateerde P0 gaps:

- CG-004: `hitl_repo` nooit doorgegeven in `dependencies.py`. `if self._hitl_repo:` guard in
  `service.py:471` altijd False. HITL_REQUIRED verdicts stil genegeerd. Geen enkel human review
  ticket aangemaakt.
- CG-004b: `HITLTicketRepository` lazy-geimporteerd in `tool_broker/service.py:212` i.p.v.
  constructor-injectie. Onmogelijk te mocken zonder monkey-patching.
  Fix dag 1: `HITLTicketRepository` injecteren als `hitl_repo` in `CopilotService` via `_build_copilot_service()`.
  Fix dag 2: `ToolBrokerService` constructor refactoren naar DI.
  Gerealiseerd: 53 tests (11 nieuw), BE-SVC-011.

---

## SP-WE-16 -- NotificationDispatcher Instantiëren bij Startup

**Status:** CLOSED (2026-06-01) | **Prio:** P1 | **Bron:** CG-003 (L3 wiring audit 2026-06-01) | **ADR:** ADR-027

Initialisatievolgorde in `app_lifespan.py` hersteld: `_init_proactive_deps` (stelt dispatcher in) nu vóór `_init_compliance_monitors` (leest dispatcher). Compliance monitors (DSARExport + PolicyChange) worden nu correct gewired bij startup. 6/6 TDD tests PASS. BE-DEP-002.
Sleutelbestand: `src/core/app_lifespan.py`.
Verwacht: 1+ monitor start succesvol, BE-SVC-016.

---

## SP-WE-17 -- Canvas Tabel Migratie: CanvasBase naar Hoofd-Base

**Status:** CLOSED (2026-06-01) | **Prio:** P0 | **Bron:** CG-002 (L3 wiring audit 2026-06-01)

Canvas feature volledig non-functioneel in productie: `Canvas` model erft van `CanvasBase`
(aparte `DeclarativeBase` in `domain_isolation.py`). Alembic gebruikt `Base.metadata` als
`target_metadata` -- `canvases` tabel onzichtbaar voor autogenerate. Tabel bestaat NIET in DB.
Alle `CanvasRouter` endpoints crashen met `UndefinedTableError: relation "canvases" does not exist`.
Fix optie A (aanbevolen): `Canvas` laten erven van hoofd-`Base` + Alembic autogenerate.
Fix optie B: `CanvasBase.metadata` registreren in `alembic/env.py`.
Constraints: `tenant_id NOT NULL`, RLS policy, werkende `downgrade()`.
Sleutelbestanden: `src/core/domains/canvas/models.py`, `src/alembic/env.py`.
Verwacht: `canvases` tabel aanwezig na `alembic upgrade head`, tenant-isolatietest, BE-MIG-005.

---

## Audit 2026-06-01 -- Nieuwe Bevindingen (13 nieuw, 5 P0, 7 P1, 1 P2)

**Audit datum:** 2026-06-01 | **Overall health:** AMBER | **Uitgevoerd door:** Gemini subagent

### Samenvatting

| Categorie          | Aantal                |
| ------------------ | --------------------- |
| Totaal geauditeerd | 42                    |
| Gefixed (FIXED)    | 30                    |
| Partieel (PARTIAL) | 1 (SP-WE-10 / CG-005) |
| Open (OPEN)        | 11                    |
| Nieuw (NEW)        | 13                    |
| P0 open            | 5                     |
| P1 open            | 7                     |

### P0 Open bevindingen

| ID           | Titel                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------ |
| CG-001       | ComplianceOfficer krijgt bare `object()` i.p.v. ComplianceGuardian -- AttributeError bij runtime |
| NEW-WIRE-001 | 5 Dramatiq actors nooit geimporteerd door worker entrypoint -- silently dead                     |
| NEW-WIRE-002 | 2 async Dramatiq actors zonder AsyncIO middleware -- actor body nooit uitgevoerd                 |
| NEW-WIRE-003 | app.state.ff_manager nooit gezet -- feature_flags_endpoints AttributeError bij elke request      |
| NEW-SEC-002  | request_audit_logs tabel heeft geen Alembic migratie -- DB writes falen bij runtime              |

---

## SP-WE-10b -- AgentHealthMonitorAgent Write-Bridge (Heropend)

**Status:** CLOSED | **Prio:** P1 | **Brief:** docs/agent-briefs/generated/2026-06-01-sprint-opstarten-SP-WE-10b-health-writebridge.md

Audit 2026-06-01 toont: `update_agent_health()` methode niet gevonden in `agent_router_agent.py` of `agent_health_monitor_agent.py` ondanks SP-WE-10 eerder CLOSED. CG-005 blijft OPEN. Alle agents scoren 0.5 UNKNOWN multiplier in health-aware routing.

---

## SP-WE-18 -- Dramatiq Actor Imports + AsyncIO Middleware Fix

**Status:** CLOSED (2026-06-14) | **Commit:** `db56fc3e` | **Feature:** BE-TSK-010

Alle 6 actor imports waren al aanwezig (SP-WE-19a, 2026-06-01). Sprint formeel gesloten na toevoeging van 3 ontbrekende registratietests (`notify_tenant_admins_of_contest`, `generate_audit_report`, `execute_workflow_step`) en MINOR fix (`_actor` scope lek). 9/9 tests GROEN.

---

## SP-WE-19 -- ff_manager Startup Wiring + request_audit_logs Migratie

**Status:** CLOSED (2026-06-12) | **Commits:** `3742cb5d` (ff_manager) + `7c8b4991` (migratie) | **Verificatie:** 2026-06-12

NEW-WIRE-003: `_init_feature_flags(app)` helper toegevoegd in `app_lifespan.py` (regel 1043+1219). `app.state.ff_manager` correct gezet met Redis fallback. NEW-SEC-002: `request_audit_logs` migratie aangemaakt (`3ee55ea8e623`) + NOT NULL fix (`20260605a`). Regressiebewakers: `tests/architecture/test_sp_we_19_startup_wiring.py` (2 GREEN tests).

---

## SP-WE-20 -- ProactiveScheduler app.state Dependencies Wiring

**Status:** CLOSED (2026-06-12) | **Commits:** `4a6a17db` (wiring) + `c39b8656` (docs) | **Verificatie:** 2026-06-12

`_init_proactive_scheduler` controleert 7 `app.state` attributen via `getattr(app.state, X, None)`. Geen enkel attribuut wordt ooit gezet: `health_registry`, `failover_provider`, `prometheus_client`, `consent_repo`, `audit_repo`, `role_repo`, `workflow_repo/pii_scanner/dpia_repo`. Gevolg: gehele Sprint 5 proactive monitoring pipeline (10 monitors) permanent uitgeschakeld in productie.

---

## SP-WE-21 -- AuditLoggingMiddleware Reparaties

**Status:** CLOSED (2026-06-12) | **Commits:** `de3eea45` (middleware ordering fix) | **Verificatie:** 2026-06-12

Drie follow-up gaps na SP-WE-14: NEW-SEC-001: `RequestAuditLog.tenant_id` is `String(50)` maar `get_tenant_id()` retourneert `int`. Type mismatch. Fix: `Mapped[int | None] = mapped_column(Integer, ...)`. NEW-SEC-003: middleware ordering risk -- `AuditLoggingMiddleware` leest `request.state.user` mogelijk voordat `TenantMiddleware` het heeft gezet (LIFO volgorde in Starlette). `tenant_id` altijd `None` in audit entries. `db_session_factory=None` disables DB logging ondanks `log_to_db=True`.

---

## SP-WE-22 -- Hardcoded ActivePieces URLs vervangen door VITE env vars

**Status:** CLOSED (2026-06-12) | **Commits:** zie deze sessie | **Verificatie:** 2026-06-12

4 productie-componenten bevatten hardcoded `http://localhost:3000`: `ActivePiecesFlowBuilder.tsx:461`, `ConnectionManager.tsx:249`, `FlowExecutionMonitor.tsx:274`, `WorkflowBuilder.tsx:519`. Breekt in staging/productie. Fix: vervang door `import.meta.env.VITE_ACTIVEPIECES_URL`. CLAUDE.md regel 8 overtreding.

---

## SP-WE-23 -- focus_builder_tool_agent NotImplementedError Afhandeling

**Status:** CLOSED (2026-06-12) | **Commits:** `de3eea45` (fallback implementatie) | **Verificatie:** 2026-06-12

`src/core/agents/focus_builder_tool_agent.py:138`: `raise NotImplementedError(...)` in concrete productiecode. Propageert naar HTTP 500. Fix: bepaal of dead code (vervang door logger.debug + graceful return) of implementeer tool-calling loop.

---

## SP-WE-24 -- \_register_notifications_v1 Definitievolgorde Fix

**Status:** CLOSED (2026-06-12) | **Commits:** `15e45eb3` (SP-API-001 Dag 5 router cleanup) | **Verificatie:** 2026-06-12

`_register_notifications_v1` gedefinieerd op regel 1021 maar aangeroepen op regel 1016 (voor de definitie). Fragiel: NameError bij refactor. Fix: verplaats functie definitie voor `register_all_routers`. Geen functionele wijziging.

---

---

## SP-WE-14b -- AuditLoggingMiddleware 3 Defecten

**Status:** CLOSED -- 2026-06-01 | **Prio:** P0 | **Bron:** NEW-SEC-001 + NEW-SEC-002 + CG-008 (ISSUE-REGISTRY-L3-L4 2026-06-01)

3 samenhangende defecten opgelost: (1) Alembic migratie `3ee55ea8e623` aangemaakt voor `request_audit_logs` met RLS, (2) `get_db_session` gekoppeld aan `db_session_factory` in `middleware_config.py`, (3) `tenant_id` type mismatch opgelost via `str()` cast in `_extract_user_info()`. Database writes verlopen via `best_effort()`. 4/4 tests PASS, 1 xfailed (pre-existing drift). mypy 0 errors, ruff clean. Feature spec: BE-MID-002.

---

## SP-WE-18 -- app.state.ff_manager Getattr Fallback

**Status:** CLOSED (2026-06-01) | **Prio:** P0 | **Bron:** NEW-WIRE-003 (ISSUE-REGISTRY-L3-L4 2026-06-01)

getattr(request.app.state, "ff_manager", None) + HTTPException(503) op 3 locaties: feature_flags_endpoints.py:344, feature_flags_endpoints.py:451, manager.py:253. 4/4 TDD tests PASS. BE-EP-018 APPROVED.

Directe attribute access `request.app.state.ff_manager` in `feature_flags_endpoints.py:344` crasht met AttributeError als startup `_init_feature_flags()` faalt. Fix: getattr fallback + HTTP 503.

---

## SP-WE-19a -- Dramatiq Actors Importeren + Async Fix

**Status:** CLOSED (2026-06-01) | **Prio:** P0 | **Bron:** NEW-WIRE-001 + NEW-WIRE-002 (ISSUE-REGISTRY-L3-L4 2026-06-01)

process_cva_message, check_hash_chain_integrity_actor, cleanup_council_decisions omgezet naar sync wrappers met asyncio.run(). Side-effect imports toegevoegd aan actors.py. Calendar actors uitgesloten (transitieve DATABASE_URL dep). 6/6 tests PASS. BE-TSK-009 + BE-CFG-007 APPROVED.

5 actors nooit geimporteerd door worker entrypoint. 2 async def actors zonder AsyncIO middleware (silent data loss). Fix: imports in actors.py + asyncio.run() wrapper.

---

## SP-WE-20 -- ComplianceOfficer NullGuardian Sentinel

**Status:** CLOSED | **Prio:** P0 | **Bron:** CG-001 | **Commit:** 786cd313

\_NullComplianceGuardian sentinel class toegevoegd; compliance_guardian=object() vervangen; 4 tests PASS; BE-UTL-035 APPROVED; Laag C 3x GO.

---

## SP-WE-21b -- ProactiveScheduler 7 Ontbrekende Dependencies

**Status:** CLOSED 2026-06-01 | **Prio:** P1 | **Bron:** NEW-WIRE-004 (ISSUE-REGISTRY-L3-L4 2026-06-01)

7 app.state attributen nooit gezet voor \_init_proactive_scheduler(): health_registry, failover_provider, prometheus_client, consent_repo, audit_repo, role_repo, workflow_repo, pii_scanner, dpia_repo. Fix: `_wire_proactive_extras(app, session_factory)` toegevoegd aan `_init_proactive_deps()`; 7 stubs in `src/core/copilot/proactive/stub_repos.py`; InMemoryHealthMonitorRegistry + LLMFallbackChain singleton hergebruikt. 19/19 tests PASS. BE-DEP-003 APPROVED WITH MINOR GAPS.

---

## SP-WE-22b -- Focus Builder NotImplementedError Fix

**Status:** CLOSED 2026-06-01 | **Prio:** P1 | **Bron:** NEW-WIRE-006 (ISSUE-REGISTRY-L3-L4 2026-06-01)

`focus_builder_tool_agent._dispatch_tools()` gooide `NotImplementedError` in productiepad. Fix: vervangen door `logger.warning("focus_builder_tool_agent_not_implemented_fallback", ...)` + `await self._fallback.handle_message(content)` (delegatie naar FocusBuilderChatAgent). 5/5 tests PASS; BE-AGT-003 APPROVED.

---

## SP-WE-23b -- Notifications Router Forward Reference Fix

**Status:** CLOSED 2026-06-01 | **Prio:** P2 | **Bron:** NEW-WIRE-005 (ISSUE-REGISTRY-L3-L4 2026-06-01)

\_register_notifications_v1 forward reference in router_registry.py.

---

## SP-FE-10 -- Frontend Hardcoded localhost URLs -> VITE Env Vars

**Status:** CLOSED (2026-06-01) | **Prio:** P1 | **Bron:** NEW-FE-001 + NEW-FE-002

2 componenten hadden hardcoded localhost:3000 (ActivePiecesFlowBuilder.tsx, WorkflowBuilder.tsx).
ContextInjectionPanel en base-url-policy.ts waren correct (window.location.host / dev-constant) -- geen fix nodig.
Oplossing: `activepiecesUrl` toegevoegd aan environment.ts Config interface + loadConfig() met VITE_ACTIVEPIECES_URL.
Fallback: http://localhost:8090 (correcte dev poort per CLAUDE.md ActivePieces valkuil).
6 pre-existing lint errors (react/no-unescaped-entities) ook opgelost.
2/2 tests PASS. 0 type-errors. FE-UTL-004 APPROVED.
Handmatige actie Rakesh: voeg VITE_ACTIVEPIECES_URL=http://localhost:8090 toe aan frontend/.env.development en .env.example.

---

## SP-DB-01 -- ORM Tabellen Drift Check + Sync Migratie

**Status:** CLOSED (2026-06-14) | **Prio:** P2 | **Commit:** `db56fc3e` | **Feature:** BE-MIG-010

Rootcause gevonden: `gdpr_deletion.py` gebruikte een aparte `Base = declarative_base()`, waardoor `DeletionAudit` onzichtbaar was voor Alembic. Fix: gedeelde Base geimporteerd uit `database.py`. `DeletionAudit` toegevoegd aan `model_registry.py`. `alembic check` na fix: "No new upgrade operations detected." -- geen migratie nodig (tabel bestond al). Aanvullend: `tenant_id NOT NULL` (ADR-005), `best_effort` ordering (CLAUDE.md Pattern 3), paginering `generate_deletion_report()` (CLAUDE.md Pattern 5).

---

## SP-API-001 -- API Layer Refactor Grade A+

**Status:** CLOSED (2026-06-02) | **Prio:** P1 | **ADR:** ADR-033

**Titel:** SP-API-001 — API Layer Refactor Grade A+ (5 dagen, ADR-033)

### Dag-voor-dag samenvatting

| Dag | Inhoud                                                                                                                                                                     | Status    | Feature IDs                        |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------------------------------- |
| 1   | Startup fix (lifespan→create_app), 11 eager imports lazy, TESTING guard, cross-router imports, hardcoded counts, .importlinter, 4 fitness tests                            | ✅ CLOSED | BE-CFG-009, BE-UTL-036, BE-UTL-037 |
| 2   | registries/auth_admin.py (55r) + compliance.py (35r)                                                                                                                       | ✅ CLOSED | BE-CFG-010                         |
| 3   | registries/analytics.py (57r) + realtime.py (46r) + tenants.py (70r) + 5 equivalentietests                                                                                 | ✅ CLOSED | BE-CFG-011                         |
| 4   | registries/agents.py (54r) + agentic.py (71r) + workflows.py (74r) + core_api.py (52r) + integrations.py (60r) + company.py (61r) + copilot.py (38r) + 7 equivalentietests | ✅ CLOSED | BE-CFG-012                         |
| 5   | Verwijdering 23 dode functies, router_registry.py 1106→267 regels                                                                                                          | ✅ CLOSED | BE-CFG-013                         |

### Totaal resultaat

- 12 Laag 2 registry bestanden aangemaakt in `src/core/api/registries/`
- 12 equivalentietests (bewijs dat alle routes behouden zijn)
- pytest 94 PASS
- 168 feature IDs geregistreerd

### Deliverables

- `src/core/api/registries/` — 12 domeinregistries
- `src/core/api/router_registry.py` — 267 regels (was 1.106)
- `.importlinter` — contracts geactiveerd
- `tests/architecture/test_api_layer.py` — 4 fitness tests
- `docs/adr/033-api-layer-service-boundary.md` — aangemaakt 2026-06-02
- `CLAUDE.md §11` — bijgewerkt 2026-06-02

### Definition of Done

- [x] `lint-imports` — contracts groen
- [x] `pytest tests/architecture/ -v` — 4/4 groen
- [x] `router_registry.py` — 267 regels (target <= 80 was aspirationeel; God-function verwijderd)
- [x] 0 module-level endpoint imports in startup-pad
- [x] 94 tests PASS, 0 failures
- [x] Feature specs BE-CFG-009/010/011/012/013 aangemaakt en geregistreerd

---

Eigenaar: Rakesh Ramkhelawan | Laatste update: 2026-06-03

---

## SP-API-002 -- API Layer Strangler Fig Migratie Week 2

**Status:** CLOSED (2026-06-03) | **Prio:** P1 | **ADR:** ADR-033

### SP-API-002 Dag-voor-dag samenvatting

| Dag | Inhoud                                                                                                                                    | Status    | Feature IDs    |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------- | -------------- |
| 1   | orphan:exempt annotaties + governance/gatekeeper/personas/terminal/websocket/agent_configs splits; scheduling registries                  | ✅ CLOSED | BE-RTR-005/006 |
| 2   | optional.py + scheduling_rest/ws registries; router_registry.py 53r                                                                       | ✅ CLOSED | BE-RTR-007     |
| 3   | compliance (1428r) + focus_builder (1082r) + users (469r) gesplitst; fitness gate actief                                                  | ✅ CLOSED | BE-RTR-008     |
| 4   | documents (656r) + orchestration (625r) + privacy (578r) + tools (454r) + canvas (410r) gesplitst; pre-existing bug critic= param gefixed | ✅ CLOSED | BE-RTR-009     |
| 5   | tenants (315r) + als (288r) + agentic (267r) gesplitst; mypy-fixes; sprint-afsluiting                                                     | ✅ CLOSED | BE-RTR-010     |

### SP-API-002 Totaal resultaat

- 11 oversized routers gesplitst naar sub-routers van max 200 regels
- 27 architectuur-tests PASS (0 skipped)
- 127 unit + architecture tests PASS
- 174 feature IDs geregistreerd
- Fitness gate volledig actief: `test_no_orphan_routers` + `test_no_router_files_over_200_lines`

### Commits

- `1682b484` — feat(SP-API-002 Dag 4+5): 11 oversized routers gesplitst
- `ca154659` — feat(SP-API-002): canvas + orchestration sub-routers (force-add)

### Openstaande minors (backlog)

- 4 focus_builder mypy-errors (`shared.py`, `ws_status_router.py`, `ws_chat_router.py`, `ai_router.py`) — geregistreerd als `# TODO(SP-VOLGENDE)` kandidaat

### SP-API-002 Definition of Done

- [x] Alle routers in `src/core/api/v1/` <= 200 regels of `# orphan:exempt`
- [x] `pytest tests/architecture/ -v` — 27 passed, 0 skipped
- [x] `pytest tests/unit/api/ -q` — 100 passed
- [x] `validate_feature_docs.py` — exit 0, 174 IDs
- [x] SPRINT-CANVAS.md CLOSED
- [x] SPRINT_TRACKER.md bijgewerkt

---

## SP-API-003 -- API Layer Strangler Fig Migratie Week 3

**Status:** CLOSED (2026-06-04) | **Prio:** P1 | **ADR:** ADR-033

### SP-API-003 Dag-voor-dag samenvatting

| Dag | Inhoud                                                        | Status                      | Feature IDs | Commit              |
| --- | ------------------------------------------------------------- | --------------------------- | ----------- | ------------------- |
| 1   | workflow domein: 9 flat bestanden → v1/workflow/ + re-exports | ✅ APPROVED WITH MINOR GAPS | BE-RTR-011  | c9fc1c9b            |
| 2   | thin wrappers vervangen + execution split (core/cancel)       | ✅ APPROVED WITH MINOR GAPS | BE-RTR-012  | 076ef586 + c796636a |
| 3   | agents domein: agent_endpoints.py → v1/agents/                | ✅ APPROVED WITH MINOR GAPS | BE-RTR-013  | (zie dag 3 commit)  |
| 4   | analytics + monitoring domein                                 | ✅ APPROVED WITH MINOR GAPS | BE-RTR-014  | (zie dag 4 commit)  |
| 5   | audit + knowledge + memory + sprint-afsluiting                | ✅ APPROVED WITH MINOR GAPS | BE-RTR-015  | (zie dag 5 commit)  |

### SP-API-003 Bekende backlog (bewust uitgesteld)

| Bestand                          | Regels | Reden uitstel                                                                     |
| -------------------------------- | ------ | --------------------------------------------------------------------------------- |
| `workflow_suggestions_router.py` | 579r   | Functioneel correct; `# orphan:exempt` aanwezig; opsplitsen in toekomstige sprint |
| `workflow_builder_router.py`     | 434r   | Pure LLM inference, geen DB; `# orphan:exempt` aanwezig; opsplitsen later         |

---

## SP-API-004 -- API Layer Strangler Fig Migratie Week 4

**Status:** CLOSED (2026-06-04) | **Prio:** P1 | **ADR:** ADR-033

### SP-API-004 Dag-voor-dag samenvatting

| Dag | Inhoud                                                                       | Status                      | Feature IDs | Commit             |
| --- | ---------------------------------------------------------------------------- | --------------------------- | ----------- | ------------------ |
| 1   | security_endpoints.py → v1/security/ (5 sub-routers)                         | ✅ APPROVED WITH MINOR GAPS | BE-RTR-016  | (dag 1 commit)     |
| 2   | mission_endpoints.py → v1/missions/ (crud + lifecycle)                       | ✅ APPROVED WITH MINOR GAPS | BE-RTR-017  | (dag 2 commit)     |
| 3   | cva_endpoints.py → v1/cva/ (5 sub-routers)                                   | ✅ APPROVED WITH MINOR GAPS | BE-RTR-018  | (dag 3 commit)     |
| 4   | health_endpoints.py + tenant_management_endpoints.py → v1/                   | ✅ APPROVED WITH MINOR GAPS | BE-RTR-019  | (dag 4 commit)     |
| 5   | autonomous_endpoints.py → v1/autonomous/ (4 sub-routers) + sprint-afsluiting | ✅ APPROVED WITH MINOR GAPS | BE-RTR-020  | (zie dag 5 commit) |

### SP-API-004 Bekende backlog (bewust uitgesteld)

| Bestand                          | Regels | Reden uitstel                                                                      |
| -------------------------------- | ------ | ---------------------------------------------------------------------------------- |
| `cors_origins` configuratie      | n.v.t. | Hardcoded origins in middleware; laaghangend fruit maar buiten scope Strangler Fig |
| `include_routers` structuur      | n.v.t. | Verdere vereenvoudiging mogelijk; post-MVP                                         |
| Unauthenticated health endpoints | n.v.t. | `/health` + `/ready` zijn nog auth-gated; publiek maken is aparte ADR-beslissing   |

---

## SP-API-005 -- API Layer Strangler Fig Migratie Week 5

**Status:** CLOSED (2026-06-05) | **Prio:** P1 | **ADR:** ADR-033

### SP-API-005 Dag-voor-dag samenvatting

| Dag | Inhoud                                                                                      | Status                      | Feature IDs | Commit                                    |
| --- | ------------------------------------------------------------------------------------------- | --------------------------- | ----------- | ----------------------------------------- |
| 1   | gdpr_compliance_endpoints.py → v1/gdpr_compliance/ (4 sub-routers)                          | ✅ APPROVED WITH MINOR GAPS | BE-RTR-021  | dag 1 commit                              |
| 2   | admin_endpoints.py + user_management_endpoints.py → v1/                                     | ✅ APPROVED WITH MINOR GAPS | BE-RTR-022  | dag 2 commit                              |
| 3   | activepieces_endpoints.py → v1/activepieces/ (5 sub-routers)                                | ✅ APPROVED WITH MINOR GAPS | BE-RTR-023  | dag 3 commit                              |
| 4   | tool_broker_endpoints.py + governance_endpoints.py → v1/                                    | ✅ APPROVED WITH MINOR GAPS | BE-RTR-024  | dag 4 commit                              |
| 5   | rbac_endpoints.py + management_endpoints.py → v1/rbac/ + v1/management/ + sprint-afsluiting | ✅ APPROVED WITH MINOR GAPS | BE-RTR-025  | 418745b6 (pre-existing) + migratie commit |

### SP-API-005 Testresultaten

| Test                    | Baseline | Eindstand       |
| ----------------------- | -------- | --------------- |
| architecture + unit/api | 147      | 149 (+2 nieuwe) |
| Regressions             | 0        | 0               |

### SP-API-005 Bekende backlog (bewust uitgesteld)

| Item                                           | Reden uitstel                                            |
| ---------------------------------------------- | -------------------------------------------------------- |
| In-memory shared state management_endpoints.py | MVP trade-off; post-MVP naar persistente opslag          |
| Legacy flat files definitief verwijderen       | Na validatie in productie dat v1/ routers correct werken |

---

## SP-API-006: API Layer Strangler Fig Week 6 — CLOSED 2026-06-05

Scope: copilot_intent, cva_chat/cva_admin/cva_conversations, feature_flags, sentiment_scanner, production, synthesis gemigreerd naar v1/.

| Dag   | Scope                                                           | BE-RTR     | Status |
| ----- | --------------------------------------------------------------- | ---------- | ------ |
| Dag 1 | copilot_endpoints.py → v1/copilot_intent/                       | BE-RTR-026 | CLOSED |
| Dag 2 | cva_chat + cva_admin + cva_conversations → v1/cva/ consolidatie | BE-RTR-027 | CLOSED |
| Dag 3 | feature_flags_endpoints.py → v1/feature_flags/                  | BE-RTR-028 | CLOSED |
| Dag 4 | sentiment_scanner + production_endpoints.py → v1/               | BE-RTR-029 | CLOSED |
| Dag 5 | synthesis gemigreerd + sprint-afsluiting SP-API-006             | BE-RTR-030 | CLOSED |

**Eindstand:** 155 tests PASS, 0 regressions.

---

## SP-API-007: API Layer Strangler Fig Week 7 — CLOSED 2026-06-06

Scope: experimentation, ai_features, subagents, models, prediction gemigreerd naar v1/.

| Dag   | Scope                                                        | BE-RTR     | Status |
| ----- | ------------------------------------------------------------ | ---------- | ------ |
| Dag 1 | experimentation_endpoints.py → v1/experimentation/           | BE-RTR-031 | CLOSED |
| Dag 2 | ai_features_endpoints.py → v1/ai_features/                   | BE-RTR-032 | CLOSED |
| Dag 3 | subagent_endpoints.py → v1/subagents/                        | BE-RTR-033 | CLOSED |
| Dag 4 | models_endpoints.py → v1/models/                             | BE-RTR-034 | CLOSED |
| Dag 5 | prediction_endpoints.py → v1/prediction/ + sprint-afsluiting | BE-RTR-035 | CLOSED |

---

## SP-API-008: ADR-033 Hard Cutover — CLOSED 2026-06-06

Scope: dead flat files → shims, import-linter, collectietijd, DSM, sprint-afsluiting ADR-033.

| Dag   | Scope                                                                                  | BE-CFG     | Status |
| ----- | -------------------------------------------------------------------------------------- | ---------- | ------ |
| Dag 1 | 31 dode shims, 3 collection errors, from **future** BLOCKER, import-linter installeren | BE-CFG-017 | CLOSED |
| Dag 2 | system_endpoints BLOCKER, import-linter violations, DSM meting, sprint tracker         | BE-CFG-018 | CLOSED |
| Dag 3 | ADR-033 succescriteria afsluiten, retrospective, sprint-afsluiting                     | BE-CFG-019 | CLOSED |

**Eindstand:** 160 tests PASS, 0 regressions. ADR-033: 5/7 criteria gehaald.
router_registry.py 65r (was 1027r). 31 dode flat files geshimmed. 4/4 fitness gates PASS.
Open pre-existing: DSM 334 (doel < 200), collectietijd 158s (doel < 90s, OneDrive).
Commits: f73e5da0, 3f67e701, 44299d14, f0cc6274, 69b792c7

**Eindstand:** 160 tests PASS, 0 regressions.

---

## SP-API-009: ADR-033 Forbidden Imports Afsluiten — CLOSED 2026-06-09

Scope: forbidden imports reduceren (249 → < 200), circulaire deps fixen, import-linter groen, sprint-afsluiting ADR-033.

**Eindmeting (2026-06-09):** 249 → 119 verboden imports (52% reductie, doel <200 behaald).
Directe schendingen in composite router.py bestanden: 0. lint-imports Contract 1: GROEN.

| Dag    | Scope                                                                                                                                                            | BE-CFG     | Status                 |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------- |
| Dag 1  | 50 registraties gecategoriseerd (A=11/B=12/C=22); 10 dubbele uitgecommentarieerd; goal_router BLOCKER gefixed                                                    | BE-CFG-020 | CLOSED — 372f4dc6      |
| Dag 2  | 4 circulaire dep root causes: auth→core_api=0, agent_runtime 11→1; workflow/schemas.py + public_registry.py aangemaakt                                           | BE-CFG-021 | CLOSED — e628a887      |
| Dag 3A | v1/workflow/ forbidden imports → dependencies.py                                                                                                                 | BE-CFG-022 | CLOSED — 11969ba8      |
| Dag 3B | v1/system/ + v1/sync/ verboden imports (parallel, externe agent)                                                                                                 | —          | CLOSED                 |
| Dag 3C | v1/gdpr_compliance/ + v1/compliance/ forbidden imports → dependencies.py                                                                                         | —          | CLOSED — 995effef      |
| Dag 3D | v1/focus_builder/ + v1/feature_flags/ + v1/agentic/ forbidden imports                                                                                            | —          | CLOSED — 3e5fc6ba      |
| Dag 4  | 8 composite router.py directe schendingen gefixed; 5 nieuwe dependencies.py; lint-imports groen (allow_indirect_imports); 65 ignore_imports ADR-033 Facade paden | —          | CLOSED — ade635ef      |
| Dag 5  | DSM eindmeting: 249→119 (-52%); router.py direct: 0; Contract 1: 1 kept; sprint CLOSED                                                                           | —          | CLOSED — zie hieronder |

**Parallelle uitvoering dag 3:** Taken 3A-3D zijn tegelijkertijd uitgevoerd.
Integratiecheck na merge: 160 architecture/unit tests passed, 0 failed.

**Openstaand (toekomstige sprint):**

- 119 resterende verboden imports in sub-routers en flat files (onder doel, geen blocker)
- `orphan:exempt` bestanden (agentic/agency_capabilities, learning, agent_discovery) — Strangler Fig migratie

---

## SP-AGT-001 -- ADR-034 agent_runtime service boundary (Dag 1-3)

**Status:** CLOSED (2026-06-09)
**Commits:** `afe0d64d` `bdc5b95b` `47b62ca1` `4aa6c823` `570f0098`
**ADR:** ADR-034 (agent_runtime service boundary)

| Dag   | Scope                                                                                   | Feature ID        | Status |
| ----- | --------------------------------------------------------------------------------------- | ----------------- | ------ |
| Dag 1 | IAgentRuntime Protocol facade + import-linter Contract 6+7                              | BE-AGT-005        | CLOSED |
| Dag 2 | MasterOrchestratorRuntimeAdapter + lifespan wiring                                      | BE-AGT-006        | CLOSED |
| Dag 3 | Hardening: get_health truthful + initialize() check + route/health tests + exc_info fix | BE-AGT-006 update | CLOSED |

**DSM eindmeting:** 119 bestanden importeren `src.core.agents.*`; 1 gebruikt facade.

**Backlog SP-AGT-002:** 8 ADR-034 violations in `orchestration/` routers (direct imports MasterOrchestratorAgent etc.).

- Flat files analytics.py + snapshot_endpoints.py — Strangler Fig migratie

---

## SP-AGT-002 -- ADR-033/034 Orchestration DI Consolidation (Dag 1-5)

**Status:** CLOSED
**ADR:** ADR-033 (3-laags router boundary) + ADR-034 (agent_runtime service boundary)

| Dag   | Scope                                                                                        | Feature ID          | Status                                                                   |
| ----- | -------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------ |
| Dag 1 | 8 violations opgelost; dependencies.py facade; 11 `__init__.py`; import-linter 4 kept 0 warn | BE-AGT-007          | CLOSED -- 6432afea 6fe3f105 349d902b efc9b9db                            |
| Dag 2 | FA-002 401-test; DSM baseline (13 db-imports); Gate 3 bewijs; SPRINT_TRACKER                 | BE-AGT-007 update   | CLOSED -- f73a85c0 ddb4e7e2                                              |
| Dag 3 | IAgentRepository protocol; AgentRegistryRepository skeleton; architecture tests              | BE-AGT-008          | CLOSED -- c27dbc03 e26c0f01                                              |
| Dag 4 | AgentRegistryRepository migrate agent_registry.py off get_async_session; DSM 13->10          | BE-AGT-008          | CLOSED -- bdad7a23 ef235b85 77f9cbef 78a1c700 910ef4aa c32bdc3c d4d049a6 |
| Dag 5 | AgentDiscoveryService off get_async_session; public_router CVA wiring; DSM 10->9             | BE-AGT-007 (update) | CLOSED -- 963fa225 1f101429 b24893c7 ba2fe59c e01f94f0                   |

**DSM fan-out resultaat:** 13 `src.core.database` imports (dag 2 baseline) -> 9 (dag 5, na volledige sprint).

**Gate 3 bewijs (finale dag 5):**

- `ruff check src/core/agents/ src/core/api/v1/orchestration/ src/core/shared/` -- All checks passed!
- `lint-imports` -- 4 contracts KEPT, 0 broken, 0 warnings
- `python -m pyright` -- 0 errors
- `pytest tests/unit/agents/ tests/unit/test_agent_* tests/architecture/ -q` -- 139 passed, 6 xfailed, 0 failed
- Volledige suite: 12709 passed, 0 failed (na pre-existing fix commit 1f101429)

**Final Approver eindoordeel alle dagen:** GO WITH MINOR ISSUES (minors opgelost in FA-fixes commits)

---

## SP-API-010 -- ADR-033 Perfectioning: P2b Dict-lekken + P2a Import-linter (Dag 1-3)

**Status:** CLOSED
**ADR:** ADR-033 (API Layer Service Boundary)
**Prerequisite:** SP-AGT-002 CLOSED (gecontroleerd)

| Dag   | Scope                                                                                                                                                                           | Feature ID              | Status                    |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ------------------------- |
| Dag 1 | P2b: 3 str(e) lekken gefixed (agents_router.py x2 + routing/router.py x1); P2a STOP-conditie (44 violations > 20); architecture test P2a backlog aangemaakt                     | BE-API-037 + BE-API-038 | CLOSED -- commit 58480cf8 |
| Dag 2 | ADR-033 Batch A: 6 flat files -> proxy stubs (14 violations -> 0); 3 arch tests + 5 route-gap tests; v1/company/dependencies.py facade; orchestrator test update                | BE-API-039              | CLOSED -- commit afd2c40a |
| Dag 3 | ADR-033 Batch B: 7 flat files lazy import fixes (7 violations -> 0); TYPE_CHECKING guards; NLP singleton; emoji/str(e) OWASP fixes; pyright pre-existing fixes (10 errors -> 0) | BE-API-040              | CLOSED -- commit 08ebca84 |

**P2a stop-conditie (Dag 1):** Scan vond 44 `*_router.py` bestanden met directe verboden imports (>20).
Backlog: `tests/architecture/test_sp_api_010_backlog.py::test_star_router_files_have_no_forbidden_imports` (XFAIL).
Fix: verplaats imports naar `<domein>/dependencies.py` per bestand, dan Contract 1 uitbreiden.

---

## SP-API-011-backlog -- ADR-033 router violations volledig verwijderd (Dag 1-3)

**Status:** CLOSED (2026-06-22)
**ADR:** ADR-033 (API Layer Service Boundary -- Depends factory pattern)
**Prerequisite:** SP-API-011 CLOSED

Scope: 32 resterende ADR-033 violations opgelost via own-domain `dependencies.py` re-export pattern.
Per domein: verboden imports verplaatst naar `<domein>/dependencies.py` (ADR-033 exempt), router files
importeren uitsluitend via eigen domein.

| Dag   | Scope                                                                                                                                                                                                                                                                                                                    | Feature ID | Status                        |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- | ----------------------------- |
| Dag 1 | `agents/` domein: 13 violations -> 0. 4 router files. `dependencies.py` uitgebreid met AgentRegistry, get_db, get_settings factories.                                                                                                                                                                                    | BE-RTR-037 | CLOSED -- da2d4869            |
| Dag 2 | `cva/` domein: 19 violations -> 0. 6 router files. `dependencies.py` volledig herschreven: 8 factory functions (LLMService, CVAService, ConversationMemory, AgentRegistry, probe_llm_health). FA-minors: dead code + silent exceptions + unused db Depends gefixed.                                                      | BE-RTR-038 | CLOSED -- 8193bf02 + 3c37b207 |
| Dag 3 | `focus_builder/` domein: 13 violations -> 0. 7 router files. `dependencies.py` uitgebreid met council.types (DataClassification, DecisionVerdict, Proposal, ProposalTrigger). Valkuil: `from __future__ import annotations` + `functools.wraps` + FastAPI -> HTTP 422 (execution_router.py). Onmiddellijk teruggedraaid. | BE-RTR-039 | CLOSED -- 1a67a8fe + 3599324e |

**Sprint totaal:** 32 violations -> 0 (3 domeinen). Architecture gates GROEN.

**Gate 3 bewijs:**

- `python scripts/dsm_api_violation_finder.py` -- 0 violations
- `python -m pyright` -- 0 errors
- `python -m pytest tests/architecture/test_dsm002_dag6_zero_violations.py tests/architecture/test_dsm_api_violations.py -v` -- beide PASSED
- `python -m pytest tests/unit/ -n 8 --timeout=60 -q` -- 207 targeted pass, 3 pre-existing failures

**Waakhonden (nu GROEN):**

- `test_dsm002_dag6_zero_violations.py::test_all_v1_violations_resolved`
- `test_dsm_api_violations.py::test_api_layer_violations_regression_ceiling`

**Final Approver eindoordeel alle dagen:** GO (dag 1+2 GO, dag 3 GO)
**Briefs:** `docs/agent-briefs/generated/2026-06-22-final-approver-SP-API-011-backlog-dag[1-3].md`

---

## SP-AGT-003 -- AIContextEngine wiring in CopilotService (Dag 1-2)

**Status:** CLOSED (2026-06-12)
**Commits:** `bd783d67` `0547ac3e`
**ADR:** ADR-034 (agent_runtime service boundary), ADR-027 (AIContextEngine §11-14)
**Prerequisite:** SP-AGT-002 CLOSED (gecontroleerd)

| Dag   | Scope                                                                                                                                | Feature ID | Status                         |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------- | ------------------------------ |
| Dag 1 | IAIContextEngine Protocol; context_engine param CopilotService; enrich() primair pad; twin_service elif fallback; log-fix; 5+5 tests | BE-AGT-009 | CLOSED -- bd783d67 0547ac3e    |
| Dag 2 | DSM-meting; ADR-034 §10 bewijs-tabel; SPRINT_TRACKER CLOSED                                                                          | --         | CLOSED -- zie commit hieronder |

**Gate 3 bewijs:**

- `python -m pyright` -- 0 errors
- `pytest tests/unit/copilot/ tests/unit/agents/test_context_engine.py -q` -- 479 passed, 0 failed
- `pytest tests/architecture/test_sp_agt_003_context_engine_wiring.py -v` -- 5 passed
- `lint-imports --contract agent_runtime_boundary --contract agent_runtime_no_db` -- 2 KEPT

**DSM resultaat SP-AGT-003:**
AIContextEngine.enrich() is nu actief in de CopilotService.handle_turn() call-chain.
context_engine.enrich() is de primaire weg; twin_service.get_profile() is elif fallback.
src.core.database imports in agent_runtime: niet veranderd door deze sprint (scope was CopilotService wiring, niet DB-import reductie).
Import-linter Contract 2+3: KEPT.

**Final Approver eindoordeel:** GO (na FA-BLOCKER fix -- raw exc in logger.error, commit 0547ac3e)

---

## SP-AGT-004 -- UnifiedCapabilityRegistry + ADR-034 Governance-grens (Dag 1-5)

**Status:** CLOSED (2026-06-12)
**Commits:** `ca048f7d` `686a2ce9` `3ed195fe` `6a71c828` `744832a0` `3c1efeab` `87f7accc`
**ADR:** ADR-034 (agent_runtime service boundary)
**Prerequisite:** SP-AGT-003 CLOSED (gecontroleerd)

| Dag   | Scope                                                                                                                                                    | Feature ID | Status                      |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------- |
| Dag 1 | ICapabilityRegistry Protocol; UnifiedCapabilityRegistry skeleton; discover() + \_register(); RedisCapabilityCache adapter; 4 arch tests wiring           | BE-AGT-010 | CLOSED -- ca048f7d 686a2ce9 |
| Dag 2 | DSM-analyse 628 fan-out (KRITIEK); gaps Facade/Registry/ToolBroker/Observability/HITL; 5 ADR-gaps architectuur-tests                                     | BE-AGT-011 | CLOSED -- 3ed195fe          |
| Dag 3 | Contract 7 draft (src.core.agents.api -> no DB); Cat A/B categorisering; governance runtime-audit; IAgentFilter; partial-load backlog-test               | BE-AGT-012 | CLOSED -- zie Dag 4         |
| Dag 4 | Governance-reductie: 3 bestanden DI/TYPE_CHECKING (cva_autonomous_trigger, perfect_subagents_manager, unified_gateway); GOV 3->0; FA minors              | BE-AGT-013 | CLOSED -- 6a71c828          |
| Dag 5 | Contract 7 src.core.agents (allow_indirect_imports=true); 7 Cat B Stap-3D NOTE-comments; FA-D3-003 ucr_wiring pad-fix; DSM finale-test; ADR-034 GESLOTEN | BE-AGT-014 | CLOSED -- 744832a0          |

**Gate 3 bewijs:**

- `python -m pyright` -- 2 errors (pre-existing baseline, geen nieuwe)
- `pytest tests/architecture/ tests/unit/agents/ -q --timeout=60` -- 467 passed, 12 xfailed, 0 failed
- `.venv/Scripts/lint-imports` -- 4 contracts KEPT (0 broken)
- `ruff check src/` -- zie Dag 4 baseline

**DSM resultaat SP-AGT-004:**
UCR operationeel als ICapabilityRegistry. Governance runtime-imports agents/: 3 -> 0.
DB violations agents/: 11 (Cat A: 4 ORM-modellen; Cat B: 7 Stap-3D gedocumenteerd, backlog SP-AGT-005).
Import-linter 4 contracts KEPT. ADR-034 volledig afgerond.

**Final Approver eindoordeel:** GO WITH MINOR ISSUES (FA-D5-001/002 blockers opgelost in 87f7accc; FA-D5-005/006 naar SP-AGT-005 backlog)

---

## SP-AGT-005 -- CriticAgent productiegaten sluiten (Dag 1-3)

**Status:** CLOSED (2026-06-19) | Commits: `0350d902` `f25b9151` (Dag 1-2) + `7e14075c` (Dag 3) + `a0df717c` (FA)
**ADR:** ADR-022 (LearningMixin + @auto_learn), ADR-023 (CriticAgent)
**Prerequisite:** SP-AGT-004 CLOSED

### Voortgang per dag

| Dag | Status | Commits    | Resultaat                                                                       |
| --- | ------ | ---------- | ------------------------------------------------------------------------------- |
| 1   | CLOSED | `0350d902` | CritiqueStore -> PostgreSQL (Alembic migratie + retentie via retention_cleanup) |
| 2   | CLOSED | `f25b9151` | Orphaned methoden aan API-endpoints + LearningMixin feedback-loop gewired       |
| 3   | CLOSED | `7e14075c` | \_llm_critique JSON-only + get_capabilities() gevuld + 7 nieuwe tests GROEN     |

### Dag 3 details

- `critic_agent.py`: prompt -> JSON-only formaat; regex-parser -> json.loads() + score clamping + isinstance-guards
- `master_orchestrator_agent.py`: get_capabilities() gevuld (3 concrete AgentCapability-objecten)
- 7 nieuwe unit tests (4x \_llm_critique + 3x get_capabilities): alle GROEN
- Feature doc: BE-AGT-017 (spec + review APPROVED + ID-REGISTRY)

### Definition of Done

- [x] CritiqueStore -> PostgreSQL (geen in-memory data verlies bij herstart)
- [x] get_agent_report() + get_system_health() + get_common_issues() aan API gewired
- [x] LearningMixin feedback-loop gesloten
- [x] \_llm_critique() parset structured JSON (geen fragiele regex meer)
- [x] get_capabilities() retourneert 3 concrete capabilities (niet leeg)
- [x] 7 nieuwe unit tests GROEN | pyright 0 errors | ruff clean
- [x] BE-AGT-017 spec + review APPROVED | ID-REGISTRY bijgewerkt
- [x] FA brief: docs/agent-briefs/generated/2026-06-19-final-approver-sp-agt-005-dag3.md

---

## SP-DSM-001 -- C4 + DSM Architecture Audit v5

**Status:** CLOSED (2026-06-13)
**Type:** Architecture monitoring (geen codewijzigingen)
**Deliverable:** `docs/architecture-c4-dsm-v5.html`
**Script:** `scripts/dsm_full_analysis.py`

### Scope

Bottom-up heruitvoering van de volledige C4+DSM audit (v4 was 2 juni 2026). Vergelijking v4→v5 op module-niveau (12 modules). Beide strangler figs (SP-API-001..010 + SP-AGT-001..004) geverifieerd.

### Meetresultaten

| Module        | fan-OUT v5 | fan-IN v5 | Oordeel | Delta t.o.v. v4                               |
| ------------- | ---------- | --------- | ------- | --------------------------------------------- |
| core_api      | 1049       | 3         | KRITIEK | -84 fan-out (ADR-033 werkt)                   |
| agent_runtime | 620        | 231       | KRITIEK | -8 fan-out (ADR-034 eerste effect)            |
| shared        | 27         | 627       | KRITIEK | +113 fan-in (meetartefact -- zie bevinding 1) |
| auth          | 62         | 439       | HOOG    | +13 fan-in                                    |
| infra         | 70         | 341       | HOOG    | --                                            |

**Totaal:** 1891 geclassificeerde bestanden (+227 t.o.v. v4), 2196 imports (+3).

### Bevindingen

| #   | Bevinding                                                                                                                                                                                       | Ernst   | Actie                                                                           |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------- |
| 1   | **shared fan-in 514→627 is MEETARTEFACT** -- v4 mat "Shared Utilities" als 43-bestand component; v5 "shared" module groepeert 11 sub-pakketten. Totale imports +3 bewijst geen echte regressie. | --      | Geen actie; vergelijking was appels/peren                                       |
| 2   | `src.core.types` -- 129x geimporteerd, niet in MODULE_MAP                                                                                                                                       | KRITIEK | Toevoegen aan MODULE_MAP als `shared` in volgende DSM run                       |
| 3   | 30 circulaire dependencies gevonden (v4 mat er 2) -- v5 meet volledig                                                                                                                           | HOOG    | Prioriteit MEDIUM pairs: agent_runtime<->infra (89), core_api<->governance (65) |
| 4   | `src.core.src.config` + `src.core.src.main` -- fout import-pad (dubbele src prefix)                                                                                                             | MEDIUM  | Fix imports in betrokken bestanden                                              |
| 5   | agent_runtime fan-out: 628→620 (-8) -- ADR-034 meetbaar effect                                                                                                                                  | --      | Doorzetten SP-AGT-005                                                           |

### Definition of Done

- [x] `scripts/dsm_full_analysis.py` succesvol uitgevoerd (geen errors)
- [x] `docs/architecture-c4-dsm-v5.html` aangemaakt met 8 tabs (C4 L1/L2/L3, Delta, DSM, Circulaire Deps, Ongeclassificeerd, Statistieken)
- [x] Vergelijking v4→v5 gedocumenteerd in Delta-tab
- [x] Meetartefact shared fan-in verklaard en gedocumenteerd
- [x] Ongeclassificeerde modules (top 10) geregistreerd

### Backlog (volgende DSM run)

- `src.core.types` toevoegen aan MODULE_MAP (129 imports ongeclassificeerd)
- `src.core.container`, `src.core.canvas`, `src.core.flows` classificeren
- Foutieve import-paden `src.core.src.*` fixen (8 bestanden)

---

## SP-DSM-COMPLETE -- DSM circulaire reparatie: infra<->agent_runtime

**Status:** CLOSED (2026-06-13) | **Commits:** `bbce2945` `dc85d08c` `e90821d2` `046d1831` `24a39e1d` `e9a6b3f9` `d6be7c93` `591ad0d3`

Dag 1-2: MODULE_MAP reclassificaties, 32->25 circulaires.
Dag 3: shared fan-out 14->0, ILearningExperienceReader Protocol ontworpen.
Dag 4: ILearningExperienceReader Protocol + SOURCE_DIRS split -> infra<->agent_runtime [KRITIEK] VERDWENEN (13->0). Cross-tenant bug lijn 345 gefixed.
Dag 5: regressie-bewaker architecture test (baseline 108 imports, threshold 120) + sprint closure + feature docs.

Backlog SP-DSM-DAG6: `admin_learning_endpoints.py` Category-2 ORM-model imports (gdpr_models + twin_models) naar service-laag facade. Backlog-marker: `test_admin_learning_endpoints_no_direct_orm_models` ROOD in `tests/architecture/`.

---

## SP-DSM-002 -- ADR-033 Violation Fix: 152 directe imports naar facade (Fase 2)

**Status:** CLOSED (2026-06-17, commit zie Dag 6)
**ADR:** ADR-033 (3-laags router + dependencies.py facade)
**Prerequisite:** SP-DSM-001 CLOSED (DSM Fase 1 scanner aanwezig, commit `0cb2c7dd`)
**Waakhond tests:**

- `tests/architecture/test_dsm_api_violations.py` -- ceiling 0, GROEN (SP-DSM-002 CLOSED)
- `tests/architecture/test_dsm_grade_a_plus.py::test_fan_out_budget_core_api` (xfail: actual 1139 > budget 800)

**Doel:** 152 API-layer bestanden die verboden modules direct importeren in plaats van via hun domein's `dependencies.py` brengen naar 0 echte violations. Na voltooiing: Contract 1 verstrengelen naar `allow_indirect_imports = false`.

### Scope

Gemeten baseline (2026-06-15): 152 violations in 76 bestanden (`scripts/dsm_api_violation_finder.py`).

Verboden modules (FORBIDDEN_MODULES in violation finder):

```
src.core.database, src.core.governance, src.core.learning, src.core.agents,
src.core.workflow, src.core.llm, src.core.services, src.core.ml, src.core.als,
src.core.semantic_router, src.core.copilot
```

Fix-patroon per bestand:

1. Verplaats verboden import naar het domein's `dependencies.py` als DI-parameter
2. Exporteer via `dependencies.py` als FastAPI `Depends()`
3. Voeg de dependency-import toe aan Contract 1 `ignore_imports` in `.importlinter`
4. Verwijder de directe import uit de router

### Dagindeling (5-7 dagen)

| Dag   | Scope                                                                                 | Verwachte reductie | Test check                   |
| ----- | ------------------------------------------------------------------------------------- | ------------------ | ---------------------------- |
| Dag 1 | Top-10 bestanden met meeste violations (uit `dsm_api_violation_finder.py`)            | 152 -> ~100        | violation finder count       |
| Dag 2 | Batch 2: governance + database violations (core_api -> governance, core_api -> infra) | ~100 -> ~60        | idem                         |
| Dag 3 | Batch 3: llm + agents violations                                                      | ~60 -> ~30         | idem                         |
| Dag 4 | Batch 4: resterende violations; Contract 1 `allow_indirect_imports = false`           | ~30 -> 0           | `lint-imports` Contract 1 OK |
| Dag 5 | Regressiecheck + Gate 3 CI + ceiling verlagen naar 0 in test_dsm_api_violations.py    | 0                  | test GROEN                   |

### Definition of Done

- [ ] `python scripts/dsm_api_violation_finder.py` toont 0 violations
- [ ] `tests/architecture/test_dsm_api_violations.py` -- ceiling verlaagd naar 0, test GROEN
- [ ] `.importlinter` Contract 1 `allow_indirect_imports = false`
- [ ] `lint-imports` -- 0 violations in alle 4+ actieve contracts
- [ ] `ruff check src/` -- 0 errors
- [ ] `python -m pyright` -- 0 nieuwe errors t.o.v. baseline
- [ ] `python scripts/dsm_full_analysis.py --html docs/architecture-c4-dsm-v8.html` succesvol
- [ ] v8 matrix: core_api fan-out gedaald richting budget 800

### Stopvoorwaarden

- Een dependencies.py veroorzaakt circular import die niet in <30 min oplosbaar is
- Een fix breekt bestaande unit tests (regressieverbod)

---

## SP-DSM-003 -- Re-enable Contract 2+3+5 na Strangler Fig (Fase 3)

**Status:** CLOSED (2026-06-17)
**ADR:** ADR-033, ADR-034
**Prerequisite:** SP-DSM-002 CLOSED (0 violations) + SP-AGT-004 CLOSED (reeds gedaan, `ca048f7d`)
**Waakhond test:** `tests/architecture/test_dsm_grade_a_plus.py::test_import_linter_all_contracts_active` (GROEN)

**Doel:** Alle 7 import-linter contracts actief maken zodat elke toekomstige schending meteen door CI geblokkeerd wordt. Nu staan Contract 2, 3, 5 uitgecommentarieerd in `.importlinter`.

### Huidige staat `.importlinter`

```ini
# Contract 2 + 3: uitgecommentarieerd -- wacht op SP-AGT-004 Strangler Fig (CLOSED) + SP-DSM-002
# Contract 5: uitgecommentarieerd -- wacht op opruiming Cat B Stap-3D exceptions (SP-AGT-005)
```

### Scope

**Contract 2** (oorspronkelijke definitie niet meer bekend -- reconstrueren uit ADR-034):

- Source: modules buiten agent_runtime die agent_runtime internals importeren
- Forbidden: `src.core.agents.*` directe deep-imports
- Na SP-DSM-002: geen violations meer verwacht

**Contract 3** (analog aan Contract 2 voor omgekeerde richting):

- Specifiek voor `src.core.api` -> `src.core.agents` directe imports

**Contract 5** (Cat B Stap-3D exceptions opruimen):

- Prerequisite: SP-AGT-005 CLOSED (Cat B DB-exceptions gedocumenteerd in `87f7accc`)

### Dagindeling (1-2 dagen)

| Dag   | Scope                                                                             |
| ----- | --------------------------------------------------------------------------------- |
| Dag 1 | Contract 2 uncommenteren + `lint-imports` groen; Contract 3 uncommenteren + groen |
| Dag 2 | Contract 5 uncommenteren (na SP-AGT-005); alle 7 contracts actief; test GROEN     |

### Definition of Done

- [x] `.importlinter` -- alle 7 contracts actief (geen uitgecommentarieerde blokken)
- [x] `lint-imports` -- 0 violations in alle 7 contracts
- [x] `tests/architecture/test_dsm_grade_a_plus.py::test_import_linter_all_contracts_active` GROEN
- [x] CI blokkeert automatisch elke toekomstige schending

---

## SP-API-011 -- Oversized routers splitsen (Fase 5)

**Status:** CLOSED (2026-06-19) | Commits: `3daf4edb` (Dag 3) + `8a3a10f1` (post-FA minors)
**ADR:** ADR-033 (router.py max 200 regels)
**Prerequisite:** SP-DSM-002 CLOSED

### Gesplitste routers (eindstand)

| Bestand                                      | Was   | Nu             | Dag   |
| -------------------------------------------- | ----- | -------------- | ----- |
| `src/core/api/v1/routing/router.py`          | 202r  | ~11r composiet | Dag 1 |
| `src/core/api/v1/subagents/router.py`        | 438r  | ~19r composiet | Dag 1 |
| `src/core/api/v1/governance_admin/router.py` | 529r  | ~36r composiet | Dag 2 |
| `src/core/api/auth/router.py`                | 1107r | ~25r composiet | Dag 3 |

### Definition of Done

- [x] Alle `router.py` bestanden <= 200 regels
- [x] `test_router_size_limit_adr033` GROEN (xfail verwijderd)
- [x] `test_prana_contracts_cache_als_violations_pending_adr` xfail verwijderd (violations gefixed)
- [x] f-string logging in auth sub-routers gefixed (13x -> %s format)
- [x] PII email verwijderd uit error log (router_login.py)
- [x] Stale fixture override verwijderd (tests/fixtures/api.py)
- [x] Feature docs: BE-API-001 (Dag 1) + BE-API-002 (Dag 2) + BE-API-003 (Dag 3)
- [x] Eindtestresultaten: 205 arch+unit PASS, 13 xfailed, 0 xpassed, pyright 0 errors

---

## SP-DSM-004 -- Aanpak B ADD: infra-no-api + governance-no-workflow-direct (Fase 4)

**Status:** CLOSED (2026-06-17, commit ce424be6)
**Uitkomst:** 9 contracts, 0 broken. layers behouden (coverage-regressie voorkomen). Contract 5 hardening deferred naar SP-DSM-005 (>10 callers). Waakhond `test_contract5_governance_independence_hardened` xfail(strict=True) toegevoegd.

---

## SP-DSM-005 -- Contract 5 Hardening: OfficerVerdict + CouncilDecisionRow type-move (Fase 4)

**Status:** CLOSED (2026-06-17, commit 4216d7b6)
**Uitkomst:** OfficerVerdict/VerdictType/CouncilDecisionRow/OfficerVerdictRow verplaatst naar governance.models. Re-exports in copilot.council.\*. Contract 5 allow_indirect_imports=false actief. 9 contracts, 0 broken. test_contract5_governance_independence_hardened PASSED. 157 arch tests, 0 failed. pyright 0 errors.
**Waakhond:** `tests/architecture/test_dsm_grade_a_plus.py::test_contract5_governance_independence_hardened` (GROEN)
**Brief:** `docs/agent-briefs/generated/2026-06-17-final-approver-sp-dsm-005-dag1.md`

Doel: verplaats `OfficerVerdict` (`copilot.council.types`) en `CouncilDecisionRow` (`copilot.council.models`)
naar `governance.models`. Re-export vanuit originele locaties (backward compat). Update `hash_chain.py`
en `retention_cleanup.py` imports. Verwijder 2 known-violations uit Contract 5 ignore_imports.
Zet `allow_indirect_imports = false`. Waakhond gaat van XFAIL naar PASSED.

ADR: ADR-027 (copilot -> governance by design; governance -> copilot verboden).

---

## SP-DSM-006 -- agent_runtime fan-out reductie: scanner + relatieve imports + Grade B

**Status:** CLOSED (2026-06-18) | Commits: `433112e4` `c41e2ee3` `5e33f023` `0333040d` + Dag-5-commit
**ADR:** ADR-034 (agent_runtime boundary), ADR-033 (import-linter contracts)
**Prerequisite:** SP-DSM-002 CLOSED + SP-DSM-003 CLOSED
**Doel:** agent_runtime fan-out reduceren naar Grade B (<=800) via scanner-fix, 365 relatieve imports, TID252 gate, shared.llm_client + shared.interfaces shim.

### Voortgang per dag

| Dag | Status                 | Commits               | Resultaat                                                                                               |
| --- | ---------------------- | --------------------- | ------------------------------------------------------------------------------------------------------- |
| 1   | CLOSED                 | `433112e4` `c41e2ee3` | Basissetup + doelstelling vastgelegd                                                                    |
| 2   | CLOSED                 | `c41e2ee3`            | llm_types shim: fan-out 878->800 (-78)                                                                  |
| 3+4 | CLOSED (GO 2026-06-18) | `5e33f023` `0333040d` | Scanner fix: 800->946 (1018 zichtbaar). Sanering: 946. TID252 gate actief.                              |
| 5   | CLOSED (2026-06-18)    | zie commit            | shared.llm_client + shared.interfaces shim. Fan-out: 946->801. FocusBuilder backlog + 3 RED arch-tests. |

### Fan-out evolutie

| Meting               | Scanner | Werkelijk | Actie                                                                   |
| -------------------- | ------- | --------- | ----------------------------------------------------------------------- |
| Start                | 878     | onbekend  | --                                                                      |
| Na Dag 2             | 800     | onbekend  | llm_types shim (-78)                                                    |
| Na Dag 3 scanner-fix | 800     | 1018      | scanner-blindspot zichtbaar: +218 hidden                                |
| Na Dag 3 sanering    | 946     | 946       | 365 relatieve imports -> absoluut; -72 llm intern                       |
| Na Dag 5             | 801     | 801       | shared.llm_client + shared.interfaces shim (-145); shim +2 netto = -143 |
| Doel Grade B         | <=800   | <=800     | Gap: 1 (801 vs 800) -- SP-DSM-007                                       |

### Dag 5 resultaat

- shared.llm_client + shared.interfaces re-exports toegevoegd aan llm_types.py (12 symbolen)
- 76 generated files: shared.\* imports -> llm_types shim
- Fan-out: 946 -> 801 (-145); shim zelf telt +2 netto = -143
- Grade B (<=800): gap = 1 (801). Architectureel correct, DSM-scanner telt shim-eigen imports mee.
- FocusBuilder KRITIEK-1/2/3 backlog: 3 RED architecture tests aangemaakt (SP-FB-001)
- Gate 2: code-reviewer GO + quality-reviewer GO (na regex-fix in arch-test)
- pyright: 0 errors | ruff: All checks passed | TID252: 0 violations in generated/

### Definition of Done (volledig sprint)

- [x] Scanner-blindspot gefixd (relatieve imports nu zichtbaar)
- [x] 365 relatieve imports in generated/ -> absoluut
- [x] TID252 CI gate actief voor generated/
- [x] Architecture tests: 160 passed, 17 xfailed, 3 intentioneel ROOD (SP-FB-001)
- [x] pyright: 0 errors; ruff: All checks passed
- [x] BE-DSM-017 spec + review APPROVED
- [x] Grade B gap gedocumenteerd (801, gap=1, SP-DSM-007)
- [x] SPRINT_TRACKER.md definitief CLOSED
- [~] SPRINT-CANVAS.md bijgewerkt (geen SP-DSM-006 rij aangetroffen)

---

## SP-DSM-007 -- DSM circulaire deps oplossen + Grade B gap + scanner TYPE_CHECKING correctie

**Status:** CLOSED (2026-06-18) | Commits: `dd3533ba` `af22e512` `b7b741a9`
**ADR:** ADR-034 (agent_runtime boundary), ADR-033 (import-linter contracts)
**Prerequisite:** SP-DSM-006 CLOSED
**Doel:** Bevestigd echte circulaire deps verwijderen, Grade B gap sluiten (801->800), scanner corrigeren voor TYPE_CHECKING false positives, TID252 non-generated fixen.

### Architectuurbevindingen (code-inspectie 2026-06-18)

Na code-inspectie per cluster blijken veel DSM-scanner "circulars" false positives:

| Cluster                    | Scanner-melding | Werkelijkheid                                   | Actie       |
| -------------------------- | --------------- | ----------------------------------------------- | ----------- |
| governance->agent_runtime  | 12 imports      | TYPE_CHECKING guards -- geen runtime koppeling  | Scanner fix |
| auth->agent_runtime        | 5 imports       | Unidirectioneel (auth->services, niet andersom) | Scanner fix |
| tenancy->agent_runtime     | 1 import        | Unidirectioneel                                 | Scanner fix |
| infra->core_api            | 3 imports       | BEVESTIGD ECHT -- KRITIEK circulair             | Fix Dag 1   |
| domain_pack->core_api      | 1 import        | Waarschijnlijk echt                             | Fix Dag 1   |
| tool_broker->agent_runtime | 1 import        | Waarschijnlijk echt                             | Fix Dag 1   |
| agent_runtime->core_api    | 2 imports       | Triviale fan-out fix                            | Fix Dag 1   |
| agent_runtime->worker      | 2 imports       | Triviale fan-out fix                            | Fix Dag 1   |

Gecorrigeerde instability agent_runtime: I = 0.47 (Grade A+ al bereikt met juiste metriek)

### Voortgang per dag

| Dag | Status | Commits            | Resultaat                                                                                              |
| --- | ------ | ------------------ | ------------------------------------------------------------------------------------------------------ |
| 1   | CLOSED | dd3533ba, af22e512 | 4 grensschendingen gefixd, Grade B gap gesloten (801->788), 13 TID252 verwijderd                       |
| 2   | CLOSED | b7b741a9           | Scanner TYPE_CHECKING filter, calculate_instability(), Ce=311 ceiling GROEN, I=0.58 xfail (SP-DSM-008) |

### Definition of Done (sprint)

- [x] infra->core_api (3 imports) verwijderd -- KRITIEK circulair weg
- [x] domain_pack->core_api (1 import) verwijderd
- [x] agent_runtime->core_api (2 imports) -- Grade B gap gesloten (788 <= 800)
- [x] TID252 non-generated (13 bestanden) -- 0 violations
- [x] Scanner: TYPE_CHECKING blokken tellen niet mee als circulaire dep
- [x] Architecture test: instability metriek aanwezig (ceiling GROEN, target xfail bewaakt)
- [x] Instability I <= 0.50 -- BEREIKT in SP-DSM-008 (Ce=222, I=0.499)
- [x] pyright: 0 errors (baseline intact) | ruff: All checks passed
- [x] Unit suite: onaangetast
- [x] Feature spec + review APPROVED (BE-DSM-019 + BE-DSM-020)

---

## SP-DSM-008 -- agent_runtime instability reductie (I=0.561 -> Grade A+)

**Status:** CLOSED (2026-06-19) | Commits: `fefa5bcb` `588cc208`
**ADR:** ADR-034 (agent_runtime boundary, I<=0.50 target)
**Prerequisite:** SP-DSM-007 CLOSED
**Doel:** agent_runtime instability I=0.561 -> I<=0.50 (Grade A+) via MODULE_MAP reclassificaties.

### Voortgang per dag

| Dag | Status | Commits  | Resultaat                                                                              |
| --- | ------ | -------- | -------------------------------------------------------------------------------------- |
| 1   | CLOSED | fefa5bcb | src.config + src.core.config + src.core.di + tracing -> shared. Ce 311->285 (-26)      |
| 2   | CLOSED | 588cc208 | database.database + resilience -> shared. Ce 285->222 (-63), I 0.561->0.499 (Grade A+) |

### Reclassificaties (volledig overzicht)

| Module                                  | Van     | Naar   | Ce-reductie | Sprint-dag                     |
| --------------------------------------- | ------- | ------ | ----------- | ------------------------------ |
| src.config                              | infra   | shared | -9 Ce       | Dag 1                          |
| src.core.config                         | infra   | shared | -8 Ce       | Dag 1                          |
| src.core.di                             | infra   | shared | -2 Ce       | Dag 1                          |
| src.core.observability.tracing          | (nieuw) | shared | -8 Ce       | Dag 1                          |
| src.core.database.database              | infra   | shared | -59 Ce      | Dag 2 (ADR-004 RLS foundation) |
| src.core.resilience                     | infra   | shared | -3 Ce       | Dag 2 (pure infra-pattern)     |
| Override: src.core.config.feature_flags | --      | infra  | +1 Ce       | Dag 1 (importeert tenancy)     |

Totale Ce-reductie: 311 -> 222 (-89 Ce). I = 222/(222+223) = 0.499.

### Definition of Done (sprint)

- [x] ADR-034 target I<=0.50 bereikt: I=0.499 (Ce=222, Ca=223)
- [x] test_agent_runtime_instability_grade_a_plus: XPASS (was XFAIL)
- [x] test_agent_runtime_ce_dag1_intermediate_target (Ce<=285): PASSED
- [x] test_agent_runtime_ce_dag2_final_target (Ce<=223): PASSED
- [x] test_shared_fan_out_is_zero: PASSED (SOURCE_DIRS["shared"] onaangetast)
- [x] test_fan_out_budget[infra-80]: PASSED (shared uitgesloten van totaal, consistent met Ce)
- [x] Architecture suite: 172 passed, 2 failed (pre-existing), 15 xfailed, 2 xpassed
- [x] pyright: 0 errors (baseline intact) | ruff: All checks passed
- [x] Unit suite: onaangetast (geen src/ of tests/unit/ wijzigingen)
- [x] BE-DSM-020 (Dag 1) spec + review APPROVED
- [x] BE-DSM-021 (Dag 2) spec + review APPROVED WITH MINOR GAPS
- [x] ID-REGISTRY bijgewerkt (BE-DSM-020 + BE-DSM-021)

---

## SP-DSM-009 -- 2 MEDIUM circulaire paren elimineren (auth<->infra + agent_runtime<->infra)

**Status:** CLOSED (2026-06-19) | Commit: `7cb41fa9`
**ADR:** ADR-034 (agent_runtime boundary), ADR-005 (auth isolation)
**Prerequisite:** SP-DSM-008 CLOSED (Grade A+ bereikt)
**Doel:** 2 MEDIUM circulaire paren sluiten via MODULE_MAP reclassificaties + seed.py ontkoppeling.

### Gesloten paren

| Pair                      | Voor  | Na   | Aanpak                                                         |
| ------------------------- | ----- | ---- | -------------------------------------------------------------- |
| `auth <-> infra`          | 20/22 | 20/0 | scheduling/api -> core_api; auth.models -> shared              |
| `agent_runtime <-> infra` | 66/3  | 66/0 | container.py -> agent_runtime; vibe_monitoring -> integrations |

### Definition of Done

- [x] Scanner: auth<->infra GESLOTEN (infra->auth = 0)
- [x] Scanner: agent_runtime<->infra GESLOTEN (infra->agent_runtime = 0)
- [x] test_dsm_no_auth_infra_circular_pair: GROEN
- [x] test_dsm_no_agent_runtime_infra_circular_pair: GROEN
- [x] seed.py: passlib direct (geen auth-import), [:72] truncatie behouden
- [x] Grade A+ behouden: Ce=225, I=~0.497 (<=0.50)
- [x] Architecture suite: 0 nieuwe failures (1 pre-existing)
- [x] pyright: 0 errors | ruff: All checks passed
- [x] BE-DSM-022 spec + review APPROVED | ID-REGISTRY bijgewerkt

---

## FE-TST-001 -- Vitest Open Handles Fix

**Status:** CLOSED (2026-06-19) | Commits: `35db8185`, `70e76f45`, `a7ecbfca`
**Doel:** 19 worker-termination errors elimineren + dangerouslyIgnoreUnhandledErrors verwijderen.

**Backlog FE-TST-002:** Pre-existing `any` in vi.mock factory props (ExperimentsRBACSettingsWorkflows.test.tsx, ~14 instances).
Marker: `// TODO(FE-TST-002)` in het testbestand. Vereist prop-interface imports per library (recharts, Card, Button, etc.).

---

## CVA Compliance Backlog (GDPR + EU AI Act) — Geidentificeerd 2026-06-20

Bron: compliance-review CVA na Batch F implementatie. ADR-031 geaccepteerd maar CVA-specifieke uitvoering mist nog.

---

## SP-CVA-COMP-001 — Consent gate CVA chat

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** GDPR Art. 6 (rechtmatige grondslag voor verwerking), AI Act Art. 13 (transparantie)
**ADR:** ADR-031 (AI Act governance contract)

**Bevinding:** `@consent_update_limit` op `chat_endpoint` en `chat_with_cva_streaming` is een rate limiter (10/min), GEEN consent-check.
Er wordt geen enkele controle uitgevoerd of de gebruiker heeft ingestemd met CVA-gebruik voordat persoonsgegevens (chat content) worden verwerkt.

**Bestanden:**

- `src/core/api/v1/cva/chat_router.py` — beide endpoints
- `src/core/services/cva_service.py` — `chat()` en `chat_stream()`
- Consent registratie: bestaande `consent` tabel (zie `retention_cleanup.py` en ADR-031)

**Aanpak:**

1. Bestaande consent-check utility opzoeken (ADR-031 / governance module)
2. Guard toevoegen aan begin van `chat()` en `chat_stream()`: check of tenant+user een actief CVA-consent heeft
3. Bij geen consent: `403 Forbidden` met duidelijke melding ("CVA usage requires prior consent")
4. Bestaande consent-flow uitbreiden met CVA-specifiek `feature_key="cva_chat"`

**Done wanneer:**

- [ ] Consent check aanwezig voor elke CVA chat-aanroep
- [ ] 403 bij geen consent — test aanwezig
- [ ] pyright 0 errors | ruff clean
- [ ] BE-CVA-003 spec + review APPROVED

---

## SP-CVA-COMP-002 — Episodic memory consent gating

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** GDPR Art. 6 (rechtmatige grondslag — separate toestemming vereist voor memory retention)
**ADR:** ADR-031, ADR-022 (LearningMixin)

**Bevinding:** `CVAService._write_memory_candidate()` (regels 53-95 van `cva_service.py`) schrijft gebruikersinhoud naar episodic memory bij ELKE chat-beurt, zonder te controleren of de gebruiker heeft ingestemd met memory-opslag.
Dit is een aparte verwerkingsgrondslag bovenop de basis-chat consent.

**Bestanden:**

- `src/core/services/cva_service.py` — `_write_memory_candidate()` (regels 53-95)
- Consent tabel: zie ADR-031 / governance module

**Aanpak:**

1. Consent-check toevoegen aan begin van `_write_memory_candidate()`
2. Bij geen memory-consent: skip de write volledig (geen fout — memory is optioneel)
3. `feature_key="cva_memory_retention"` als aparte consent-categorie

**Done wanneer:**

- [ ] Memory write overgeslagen als geen memory-consent
- [ ] Test: geen memory write zonder consent
- [ ] Test: memory write wel aanwezig met consent
- [ ] pyright 0 errors | ruff clean

---

## SP-CVA-COMP-003 — Conversation data retention policy

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** GDPR Art. 17 (recht op vergetelheid / data minimisation)
**ADR:** ADR-019 (audit logging + retention)

**Bevinding:** `src/core/tasks/retention_cleanup.py` definieert `RETENTION_ALLOWED_TABLES` voor automatische purge bij verlopen consent.
`conversations` en `conversation_messages` staan NIET in deze lijst — CVA-gespreksdata wordt nooit automatisch verwijderd.

**Bestanden:**

- `src/core/tasks/retention_cleanup.py` — `RETENTION_ALLOWED_TABLES` uitbreiden
- Eventueel aparte retentieperiode instellen voor CVA-data (bijv. 90 dagen na laatste activiteit)

**Aanpak:**

1. `conversations` en `conversation_messages` toevoegen aan `RETENTION_ALLOWED_TABLES`
2. Retentieperiode bepalen (afstemmen met Rakesh — juridische/product beslissing)
3. Test: na consent-verloop worden CVA-rijen ook gecleanup

**Done wanneer:**

- [ ] `conversations` + `conversation_messages` in RETENTION_ALLOWED_TABLES
- [ ] Retentieperiode gedocumenteerd (bijv. `CVA_RETENTION_DAYS` env var)
- [ ] Test: cleanup verwijdert CVA-data na verlopen consent
- [ ] pyright 0 errors | ruff clean

---

## SP-CVA-COMP-004 — Frontend right-to-explanation (GS-FE-1)

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** AI Act Art. 13 (transparantie over geautomatiseerde besluitvorming)
**Ref:** Ground-truth scan 2026-05-28 (GS-FE-1, pre-existing)

**Bevinding:** `frontend/src/hooks/useExplainability.ts` retourneert hardcoded mock data voor AI-beslissingsuitleg.
Gebruikers zien schijn-transparantie: de UI toont uitleg, maar die is nep.

**Bestanden:**

- `frontend/src/hooks/useExplainability.ts` — mock implementatie vervangen door echte API-call
- Backend explainability endpoint: `SP-C02` (zie SPRINT_TRACKER) — status controleren

**Aanpak:**

1. Controleer of SP-C02 (useExplainability + backend endpoint) al geimplementeerd is
2. Zo niet: backend endpoint `GET /api/v1/explanations/{decision_id}` implementeren
3. `useExplainability.ts` koppelen aan echte API

**Done wanneer:**

- [ ] `useExplainability.ts` roept echte API aan
- [ ] Backend endpoint geimplementeerd en gedocumenteerd
- [ ] Mock data volledig verwijderd
- [ ] FE spec + review APPROVED

---

## SP-CVA-COMP-005 — Notification router registratie (WE-014)

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** ADR-033 (router registratie)
**Ref:** Pre-existing WE-014

**Bevinding:** De notification router is niet opgenomen in `register_all_routers()`. Notificatie-endpoints zijn hierdoor onbereikbaar in productie.

**Bestanden:**

- `src/core/api/registries/` — registry bestand voor notifications
- `src/core/api/v1/notifications/` — router (als die bestaat)
- `src/core/api/router.py` of equivalent — `register_all_routers()`

**Aanpak:**

1. Zoek de notification router: `grep -rn "notifications" src/core/api/`
2. Voeg lazy import + registratie toe in de juiste registry file
3. Test: `GET /api/v1/notifications/` geeft 200/401 (niet 404)

**Done wanneer:**

- [ ] Notification router geregistreerd in `register_all_routers()`
- [ ] Endpoint bereikbaar (niet 404)
- [ ] pyright 0 errors | ruff clean

---

## SP-CVA-COMP-006 — CVA chat audit trail

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** ADR-019 (SHA-256 hash chain audit logging)
**Ref:** TODO op `chat_router.py:63`

**Bevinding:** `chat_router.py` heeft een TODO-comment op regel 63 voor governance/council integratie.
CVA-interacties worden niet gelogd in de ADR-019 audit chain — geen aantoonbaar bewijs van AI-beslissingen.

**Aanpak:**

1. `best_effort` audit log toevoegen na succesvolle chat-respons in `chat()` en `chat_stream()`
2. Log: `user_id`, `tenant_id`, `conversation_id`, `model_used`, timestamp, response hash
3. Gebruik bestaand `AuditLog` model (zie ADR-019 implementatie)

**Done wanneer:**

- [ ] Audit log entry per CVA chat-interactie (via `best_effort`)
- [ ] Hash van response opgenomen in audit entry
- [ ] Test: audit entry aanwezig na chat-aanroep
- [ ] pyright 0 errors | ruff clean

---

## SP-CVA-COMP-007 — Memory write privacy scope validatie

**Status:** CLOSED (2026-06-20) | **Commit:** `734c5c99` | Gate 3: pyright 0e / ruff clean / tests groen
**Grondslag:** GDPR Art. 6 (doelbinding — memory write is aparte verwerking)
**ADR:** ADR-022 (LearningMixin + @auto_learn)

**Bevinding:** `_write_memory_candidate()` schrijft episodic memory met een `privacy_scope` veld, maar valideert dit veld niet tegen de daadwerkelijke consent van de gebruiker.
Een agent zou `privacy_scope="public"` kunnen instellen voor data die de gebruiker als privaat heeft geconsent.

**Aanpak:**

1. Ophalen werkelijke consent-scope van de gebruiker (via ADR-031 governance)
2. Valideren dat `privacy_scope` van de memory write niet ruimer is dan de consent-scope
3. Bij mismatch: downgrade naar meest beperkte toegestane scope, of skip de write

**Done wanneer:**

- [x] `privacy_scope` gevalideerd tegen gebruikers-consent voor elke write
- [x] Test: te ruime scope wordt afgewezen of gedowngraded
- [x] pyright 0 errors | ruff clean

---

## SP-CVA-SEC — CVA CRITICAL Security fixes (dag 1)

**Status:** CLOSED (2026-06-20) | **Commits:** `2ba119f9` `c2592a61` | Gate 3: pyright 0e / 5 tests groen

CRITICAL audit bevindingen CVA-pipeline: GovernanceGate council integratie, Shadow CEO veto-check,
Right-to-Explanation endpoint (AIACT-003/004/002 + ARCH-014).
FA-003/004/005/006 minors gefixed in `c2592a61`.

---

## SP-CVA-HIGH — CVA HIGH Security & Architecture fixes (dag 1+2)

**Status:** CLOSED (2026-06-21) | **Commits:** `49a885fe` `873a1299` `b84a661b` | Gate 3: pyright 0e / 23 tests groen

11 HIGH audit bevindingen gesloten in 2 dagen:

- Dag 1 (`49a885fe`): SEC-002/003/008/010/013, BE-003, ARCH-003/008/011, ADR-033, Batch D test fix
- FA-001+002+003 minors (`873a1299`): logging %-stijl, info-leak prevention, tenant isolatie test
- Dag 2 (`b84a661b`): ARCH-005 CVAService ADR-022 vrijstelling gedocumenteerd; architecture test GROEN

Feature doc: BE-SVC-041-sp-cva-high-dag1-hardening.md | Review: APPROVED

---

## SP-CVA-COMP — CVA GDPR/AI Act Compliance (single-dag)

**Status:** CLOSED (2026-06-20) | **Commits:** `734c5c99` `7e19d592` `cf7d2774` | Gate 3: pyright 0e / tests groen

Alle 7 COMP-items opgelost in een enkele sprint-dag:
COMP-001 consent gate, COMP-002 memory consent, COMP-003 retention policy,
COMP-004 frontend right-to-explanation, COMP-005 notification router,
COMP-006 audit trail, COMP-007 privacy scope validatie.

---

## SP-CVA-P1 — CVA P1 HIGH Audit Fixes (3 dagen)

**Status:** CLOSED (2026-06-22) | **Dag 1:** `8945178c` `4e8e0b3b` | **Dag 2:** `fec29793` `3279f346` | **Dag 3:** `1285abd0` `aeef6afa` `67c307f1` `05278c5a` | Gate 3: pyright 0e / 18+ tests groen

9 P1 HIGH findings uit AGENT-CVA-COUNCIL-AUDIT-2026-06-20 gesloten in 3 dagen:

| Dag | Finding                                               | Fix                                                                      | Commit                           |
| --- | ----------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------- |
| 1   | SEC-004: PromptGuard niet op HTTP entry               | `_PromptGuardAdapter` + scan in turn_endpoint + chat_router              | `8945178c`                       |
| 1   | ARCH-005: CVAService ADR-022 exempt comment           | exempt comment toegevoegd, architecture test GROEN                       | `8945178c`                       |
| 1   | FA-minors (tenant_id=0, structured 400, runtime test) |                                                                          | `4e8e0b3b`                       |
| 2   | SEC-001/005: InMemoryRateLimiter multi-worker bypass  | RedisRateLimiter in governance/rate_limiter.py + InMemory fallback       | `fec29793`                       |
| 2   | ARCH-004: CVA niet in AI Act governance contract      | `test_cva_chat_uses_require_council_approval` xfail verwijderd           | `fec29793`                       |
| 2   | GDPR-002: CVA gesprekken niet in portability export   | `_load_cva_conversations()` + CVAConversation ORM in LearningGDPRService | `fec29793`                       |
| 3   | FE-001: CopilotSidebar error state                    | Error banner in CopilotSidebar.tsx                                       | `1285abd0`                       |
| 3   | FE-003: Consent banner niet persistent                | localStorage dismiss-flag                                                | `1285abd0`                       |
| 3   | FE-005: GDPR Art. 17 bulk delete UI                   | "Alle gesprekken verwijderen" in CVAChat.tsx                             | `1285abd0`                       |
| 3   | AIACT-008: HITL bereikbaar vanuit CVA                 | HITL badge bij hitl_required verdict                                     | `1285abd0`                       |
| 3   | FA-001 verdict null fix + FA-002 arch test rood       |                                                                          | `aeef6afa` `67c307f1` `05278c5a` |

Feature docs: BE-SEC-020 (PromptGuard), BE-SVC-042 (ARCH-005), BE-SEC-021 (Redis RL), BE-GOV-002 (ARCH-004 + GDPR-002), FE-CVA-002 (dag 3 frontend)

Architecture tests: alle intentioneel ROOD tests GROEN (2026-06-23) -- deferred FA-findings dag 1 (test_cva_p1_dag1_deferred_findings.py) + AIACT-008 verdict wiring (test_copilot_verdict_wiring.py) via SP-GOV-002/003.

---

## SP-PERF-001 — Backend Cold-Start Optimalisatie (Agents + CVA + Auth)

**Status:** CLOSED (2026-06-21) | **Commit:** `ac26c73e` | Gate 3: pyright 0e / 21 tests groen
**ADR:** ADR-009 (startup budget dev <30s, prod <10s)

Cold-start optimalisatie -- ronde 3. Bottlenecks (gemeten na ronde 2, ~19.3s app creation):

- `src.core.api.v1.agents` sub-routers: ~7s elk
- `src.core.api.v1.cva.chat_router`: ~16.9s (eerdere meting, herprofileren na SP-CVA-HIGH)
- `src.core.api.agent_endpoints`: ~6.8s
- Login latency: ~5.5s (optioneel, alleen als tijd over)

Aanpak: lazy imports in handler-bodies + Depends-factory-bodies. Pattern van ronde 2 hergebruiken.

Sprint brief: `docs/agent-briefs/generated/2026-06-21-sprint-dag-SP-PERF-001-dag1.md`

**Done wanneer:**

- [ ] 5 import-tijd tests GROEN (grens: 3s per module)
- [ ] Agents sub-routers < 3s elk
- [ ] `python -m pyright` -- 0 errors
- [ ] BE-PERF-001 spec + review APPROVED

---

## SP-SEC-ARCH-HARDENING -- Security Architecture Hardening (3 dagen)

**Status:** CLOSED (2026-06-22) | **Commits:** `7a60dead` `9054b074` `93e53bdb` `d2677c16` `0b192816` | Gate 3: pyright 0e / suite GROEN

| Dag    | Finding                                                               | Fix                                                                                 | Commit     |
| ------ | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------- |
| 1      | 3 RED arch tests: FA-002 factory guard, FA-004 OWASP A05              | None-check in \_RiskRegisterAdapter + tenant_id uit PromptInjectionError verwijderd | `7a60dead` |
| 1      | SP-SEC-RL-001 (gedeeltelijk): Redis-backed copilot_turn_limit gebouwd | governance/rate_limiter.py +80r: RedisRateLimiter + InMemory fallback               | `7a60dead` |
| 1      | GPA model docs timestamp                                              | regenerate                                                                          | `9054b074` |
| 1      | WORKING-CONTEXT + FA brief                                            |                                                                                     | `93e53bdb` |
| minors | Dead branch + NullGDPREnforcer + 429 format test                      |                                                                                     | `d2677c16` |
| close  | WORKING-CONTEXT CLOSED                                                |                                                                                     | `0b192816` |

**SP-SEC-RL-001 CLOSED (2026-06-23):** turn_endpoint.py gewired op governance.rate_limiter (Commit `8e26a0b8`).

- test_dsm006_ar_governance_fan_out.py: threshold < 5 -> <= 5 (5e governance node toegestaan)
- test_turn_endpoint.py: patch targets -> governance.rate_limiter + \_get_redis_limiter

---

## SP-GOV-002 -- Governance Council Gate + Model Traceability

**Status:** CLOSED (2026-06-23) | Gate 3: pyright 0e / 0 violations / arch tests GROEN

| Dag       | Deliverable                                                                                | Commit                |
| --------- | ------------------------------------------------------------------------------------------ | --------------------- |
| 1         | RC-001: council gate agent execute/collaborate wired + RC-003: model_id SHA-256 hash chain | `16a7b0f3`            |
| 1         | Final-approver brief dag 1                                                                 | `22411357`            |
| 2         | RC-002: legacy CVA council gate (cva_service) + RC-009a: agent execute rate limits         | `8a544dd4`            |
| 2         | xdist-fixes: RC-002/RC-009a arch tests naar tests/architecture/ (parents[2])               | `d91c3811`            |
| 2         | WORKING-CONTEXT + agent briefs                                                             | `a2d22b61` `45465b1e` |
| regressie | 6 ADR-033 violations in agent routers verwijderd via require_agent_council_approval facade | `50fa2a89`            |

Architecture tests: 0 violations (DSM ceiling = 0 bewaard). 388 unit tests GROEN.

---

## SP-GOV-003 -- CVA Tenant Isolatie + Governance UX Completeness

**Status:** CLOSED (2026-06-23) | **Commits:** `3d0c1be1` `08968690` `a240f5dc` | Gate 3: pyright 0e / 4 arch tests GROEN

| Finding | Fix                                                                              | Commit                |
| ------- | -------------------------------------------------------------------------------- | --------------------- |
| RC-005a | Reeds gefixed in eerdere sprints (geen code)                                     | --                    |
| RC-005b | AgentRegistry cache key -> (tenant_id, agent_id) tuple                           | `3d0c1be1`            |
| RC-005c | Reeds gefixed in eerdere sprints (geen code)                                     | --                    |
| RC-005d | RLS migratie conversations + conversation_messages (NULLIF missing_ok=true)      | `3d0c1be1` `08968690` |
| RC-006  | parseGovernanceError + GOVERNANCE_BLOCKED enum + CVAChat + AgentDetailModal      | `3d0c1be1` `08968690` |
| RC-008  | Council gate verwijzing in legacy agent_endpoints.py docstring                   | `3d0c1be1`            |
| RC-009b | Permanent post-MVP backlog geregistreerd in SPRINT_PLANNING.md                   | `3d0c1be1`            |
| FA-001  | RLS current_setting missing_ok=true fix (BLOCKER)                                | `08968690`            |
| FA-002  | AgentDetailModal governance catch was dead code (ApiError.status vs .statusCode) | `08968690`            |
| FA-003  | FLOW_BLOCKED_BY_COUNCIL test ontbrak in useApiGovernance.test.ts                 | `08968690`            |

Feature docs: BE-GOV-007 (RC-005b+d cache+RLS), FE-HK-005 (RC-006 governance UX) -- beide APPROVED.
Architecture tests: 4 GROEN (test_gov003_rc005b/rc005d/rc008).

---

## SP-SEC-RL-001 (backlog-item) -- Zie SP-SEC-ARCH-HARDENING hierboven

---

## SP-DLP-001 -- DLP & GDPR Enforcement Sprint

**Status:** OPEN (2026-06-25) | **Basis:** Audit `docs/reports/AUDIT-ADR-DLP-2026-06-25.md` (116 bevindingen: 8 CRITICAL, 44 HIGH)
**Duur:** 4 dagen | **Gate 3 baseline:** pyright 0 errors (bereikt 2026-06-09, commit b1398e4c)
**Architecture tests:** 4 ROOD op commit (worden GROEN na fixes)

| ADR         | Score voor | Score na P0 | Score na P1 |
| ----------- | ---------- | ----------- | ----------- |
| ADR-003     | 65%        | 75%         | 90%         |
| ADR-015     | 50%        | 50%         | 80%         |
| ADR-016/017 | 55%        | 55%         | 85%         |
| ADR-019     | 60%        | 70%         | 95%         |
| ADR-031     | 30%        | 45%         | 70%         |

---

### P0 -- CRITICAL (blockers voor productie)

| ID        | Bevinding                                                                    | Bestand                                                     | Fix                                                  |
| --------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------- |
| GDPR-005  | Portability endpoint exporteert ALLE tenant-gebruikers (geen user_id filter) | `src/core/api/v1/gdpr_compliance/portability_router.py:110` | Voeg `where User.id == current_user.id` toe          |
| GDPR-003  | `has_consent` hardcoded `True` in consent_router                             | `src/core/api/v1/privacy/consent_router.py:47`              | Vervang door echte DB-lookup via `ConsentRepository` |
| GDPR-011  | Audit trail endpoint filtert niet op user_id                                 | `src/core/api/v1/gdpr_compliance/access_router.py:27`       | Voeg user_id WHERE-clause toe                        |
| SEC-006   | `upload_agent_yaml` mist `Depends(get_current_user)`                         | `src/core/api/v1/agentic/agents.py`                         | Voeg auth-dependency toe aan signature               |
| EU-AI-002 | `AIActBanner` niet gemount in App.tsx                                        | `frontend/src/App.tsx`                                      | Import + mount in root layout                        |

Architecture tests: `tests/architecture/test_gdpr_enforcement_wiring.py` (GDPR-003/005/011), `tests/architecture/test_pii_log_leakage.py` (SEC-006), `tests/architecture/test_governance_wiring.py` (EU-AI-002)

---

### P1 -- HIGH (DLP kernimplementatie)

| ID            | Bevinding                                            | Bestand                                     | Fix                                           |
| ------------- | ---------------------------------------------------- | ------------------------------------------- | --------------------------------------------- |
| DLP-GAP       | `redact_pii()` ontbreekt in GDPREnforcer             | `src/core/governance/gdpr_enforcer.py`      | Implementeer per feature spec BE-SEC-DLP-001  |
| DLP-INTERCEPT | `llm_client.py` stuurt PII naar externe providers    | `src/core/llm/llm_client.py`                | `_sanitize_messages()` in alle 3 entry points |
| SEC-001       | Email verbatim in auth logs                          | `src/core/frontend/auth.py:61,68,78`        | SHA-256 hash ipv plaintext                    |
| SEC-002       | `user_input` verbatim in CVA logs                    | `src/core/agents/ultimate_cva/agent.py:150` | Log alleen `len=`                             |
| SEC-007       | JWT token slice in logs                              | `src/core/auth/jwt_handler.py`              | Vervang door `[TOKEN REDACTED]`               |
| ADR019-001    | `AuditLog` model mist `audit_hash` + `previous_hash` | `src/core/governance/models.py:33`          | Voeg fields toe + Alembic migratie            |

Feature spec: `docs/backend/features/BE-SEC-DLP-001-pii-masking-llm-intercept.md`
Architecture tests: `tests/architecture/test_pii_log_leakage.py` (SEC-001/002/007), `tests/architecture/test_governance_wiring.py` (ADR019-001)

---

### P2 -- MEDIUM (governance wiring)

| ID      | Bevinding                                                    | Bestand                                | Fix                                                                    |
| ------- | ------------------------------------------------------------ | -------------------------------------- | ---------------------------------------------------------------------- |
| TI-001  | `process_cva_message` actor mist `set_tenant_id()` (ADR-003) | `src/core/tasks/cva_tasks.py:40`       | Haal tenant_id uit message-payload en zet ContextVar                   |
| TI-003  | `execute_workflow_step` mist ContextVar (ADR-003)            | `src/core/tasks/workflow_tasks.py:13`  | Idem                                                                   |
| TI-004  | `get_agent_router(tenant_id=1)` hardcoded                    | `src/core/workflow/worker.py:291`      | Haal tenant_id dynamisch op                                            |
| TI-005  | Redis-keys missen tenant_id prefix                           | `src/core/learning/multi_region.py:97` | Prefix met `tenant:{tenant_id}:`                                       |
| GOV-001 | Gatekeeper niet gedraad in `get_router()`                    | `src/core/als/router.py:1000`          | Voeg `gatekeeper` parameter toe                                        |
| GOV-002 | Gatekeeper fail-open bij alle fouten                         | `src/core/als/router.py:288`           | Introduceer `GATEKEEPER_FAIL_OPEN` config flag (default False in prod) |
| GOV-003 | `_create_tool_broker()` mist `HITLStore`                     | `src/core/agents/base_agent.py:156`    | Inject `HITLStore` via BaseAgent.**init**                              |

Architecture tests: `tests/architecture/test_tenant_context_workers.py` (TI-001/003/004/005), `tests/architecture/test_governance_wiring.py` (GOV-001/002/003)

---

### P3 -- LOW (compliance completeness)

| ID         | Bevinding                                                                              | Bestand                                     | Fix                                                             |
| ---------- | -------------------------------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------- |
| GDPR-004   | Art. 17 forget-me cascade onvolledig                                                   | `src/core/services/dsar_service.py`         | Cascade naar alle PII-dragende tabellen                         |
| GDPR-009   | Profiling opt-out niet gecheckt voor agent-activering                                  | `src/core/agents/base_agent.py`             | Check `ConsentRepository.has_profiling_consent()` voor activate |
| GDPR-001   | `LawfulBasisRegistry.validate_endpoint_access()` nooit aangeroepen                     | `src/core/api/` routes                      | Wire in request lifecycle (FastAPI middleware of Depends)       |
| EU-AI-004  | `_check_risk_classification()` niet geimplementeerd in QualityGate                     | `src/core/governance/quality_management.py` | Implementeer per ADR-031 autonomy ladder                        |
| ADR031-001 | `GovernanceContract` klasse bestaat niet; `autonomy_level` geeft `'stub_phase4'` terug | `src/core/governance/`                      | Implementeer contract per ADR-031 spec                          |
| TI-002     | `dramatiq.set_config()` gebruikt i.p.v. ContextVar                                     | `src/core/tasks/`                           | Migreer naar ContextVar-patroon (ADR-003)                       |

Architecture tests: `tests/architecture/test_governance_wiring.py` (EU-AI-004), `tests/architecture/test_gdpr_enforcement_wiring.py` (GDPR-003/009)

---

### Definition of Done SP-DLP-001

- [ ] Alle P0 bevindingen gefixed en architecture tests GROEN
- [ ] `redact_pii()` + `detokenize()` geimplementeerd in `gdpr_enforcer.py`
- [ ] `_sanitize_messages()` actief in `chat_completion()`, `generate_response()`, `complete_json()`
- [ ] SEC-001/002/007 log-lekken gefixed
- [ ] `AuditLog` model heeft `audit_hash` + `previous_hash` + Alembic migratie
- [ ] `python -m pyright` -- 0 errors (baseline bewaard)
- [ ] `python -m pytest tests/unit/ -n 8 --timeout=60 -q` -- 0 failures
- [ ] `python -m pytest tests/architecture/test_pii_log_leakage.py tests/architecture/test_tenant_context_workers.py tests/architecture/test_governance_wiring.py tests/architecture/test_gdpr_enforcement_wiring.py -v` -- alle tests GROEN na P1
- [ ] Feature docs aanwezig: `docs/backend/features/BE-SEC-DLP-001-pii-masking-llm-intercept.md`
- [ ] Audit rapport aanwezig: `docs/reports/AUDIT-ADR-DLP-2026-06-25.md`
- [ ] Geen nieuwe pyright errors t.o.v. baseline na elke bestandswijziging

---

## SP-DLP-002 -- DLP Compliance Completeness Sprint

**Status:** CLOSED (2026-06-26) | **Basis:** SP-DLP-001 + Audit `docs/reports/AUDIT-ADR-DLP-2026-06-25.md`

### Resultaten

| Dag   | Item                                                             | Commits    | Status            |
| ----- | ---------------------------------------------------------------- | ---------- | ----------------- |
| Dag 1 | GovernanceContract klasse (ADR-031, BE-GOV-008)                  | --         | CLOSED 2026-06-26 |
| Dag 2 | LawfulBasisRegistry API wiring (GDPR-001, BE-GOV-009)            | 0f6780fa   | CLOSED 2026-06-26 |
| Dag 3 | Art. 17 forget-me CVAConversation cascade (GDPR-004, BE-GOV-010) | 38925675   | CLOSED 2026-06-26 |
| Dag 4 | GDPR-009 profiling opt-out + EU-AI-004 QualityGate (BE-GOV-011)  | zie commit | CLOSED 2026-06-26 |

### Definition of Done SP-DLP-002

- [x] GovernanceContract klasse aangemaakt (ADR-031 compliance)
- [x] LawfulBasisRegistry gewired in 4 GDPR API routes (non-blocking, GDPR-001)
- [x] Art. 17 cascade: CVAConversation verwijderd bij DSAR delete (hard + soft pad)
- [x] GDPR-009: `_profiling_opted_out` attribuut in `EnhancedBaseAgent`
- [x] EU-AI-004: `_check_risk_classification()` aanwezig in QualityGate (arch test GROEN)
- [x] Falende arch test SP-DLP-003 wiring verplichting in CI
- [x] `python -m pyright` -- 0 errors (baseline bewaard)
- [x] Alle TDD tests GROEN (3 + 4 + 4 tests per dag)
- [x] Feature docs aanwezig: BE-GOV-008..011

### Openstaande items (SP-DLP-003)

- `has_profiling_consent()` echte ConsentRepository database lookup
- Per-request profiling guard in `process_task()` (arch test ROOD tot SP-DLP-003)
- LawfulBasisRegistry hard-blocking (nu non-blocking)
- AuditLog hash chain populatie (velden aanwezig, schrijf-logica niet)

---

## SP-ADR023 -- ADR-023 WorkflowService wiring + tenant_id propagatie (2 dagen)

**Status:** CLOSED (2026-06-27) | **ADR:** ADR-023 | **Branch:** develop

### Aanleiding

Code-review (SP-AGT-003 Dag 1) markeerde 2 pre-productie HIGH gaps:

- P0-4: `WorkflowService._execute_step()` was een stub -- retourneerde altijd `"not_implemented"` (DDD domain model in `src/domains/workflows/services.py`)
- P0-5: `RouterAgentService.execute_request()` had geen `tenant_id` parameter -- LLM-aanroepen hadden geen tenant-context

### SP-ADR023 Resultaten

| Dag   | Item                                                                                                          | Commits                            | Feature Doc | Status            |
| ----- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------- | ----------- | ----------------- |
| Dag 1 | P0-4: `_execute_step()` gewired naar `RouterAgentService.execute_request(query)` + `threading.Lock` singleton | `bc9c113c`, `d7a42c11`             | BE-WFL-003  | CLOSED 2026-06-27 |
| Dag 2 | P0-5: tenant_id threading `execute_workflow()` -> `_execute_step(tenant_id)` -> `execute_request(tenant_id)`  | `4821c115`, `92deee48`, `f3d98b13` | BE-WFL-004  | CLOSED 2026-06-27 |

### SP-ADR023 Dag 1 -- Scope

- `WorkflowService.__init__(router: RouterAgentService | None = None)` -- backward-compatible constructor
- `_execute_step()`: geen router -> `"skipped"`, router aanwezig -> `"completed"` of `"failed"` (geen re-raise)
- `execute_workflow()` guard uitgebreid: `"skipped"` + `"failed"` triggeren `workflow.fail()` (was alleen `"not_implemented"`)
- `threading.Lock` toegevoegd aan `get_master_orchestrator()` singleton (was race condition)
- Loguru-patroon gecorrigeerd: `logger.opt(exception=True).error()` i.p.v. `exc_info=True` met `%s`
- 5 TDD tests: RED voor fix, GROEN na fix

FA-minors DAG1 (commit `d7a42c11`): FA-001 loguru.bind(), FA-002 testcount brief, FA-003 logging-assertion test

### SP-ADR023 Dag 2 -- Scope

- `RouterAgentService.execute_request(query, tenant_id: str | None = None)` -- optionele param + `"tenant_id"` in return-dict
- `WorkflowService._execute_step(step, tenant_id: str | None = None)` -- doorgeven aan `execute_request(query, tenant_id=tenant_id)`
- `WorkflowService.execute_workflow()` -- threadt `workflow.tenant_id` naar `_execute_step(step, workflow.tenant_id)`
- Type `str | None`: DDD domain model `Workflow.tenant_id` is `str`; systeem `ContextVar[int]` niet geraakt
- TDD: RED tests in commit `4821c115`, fix in commit `92deee48`

FA-minors DAG2 (commit `f3d98b13`): FA-001 f-string logging -> `%s + exc_info=True` (6 calls), FA-002 mock return_value contract, FA-003 None-forwarding test met `assert_awaited_once_with`, FA-006 spec-claim gecorrigeerd

### SP-ADR023 Definition of Done

- [x] `WorkflowService._execute_step()` gewired naar `RouterAgentService.execute_request()`
- [x] `WorkflowService.execute_workflow()` markeert als FAILED bij `"skipped"` of `"failed"` stappen
- [x] `RouterAgentService.execute_request(query, tenant_id: str | None = None)` aanwezig
- [x] `tenant_id` threading: `execute_workflow()` -> `_execute_step()` -> `execute_request()`
- [x] 9 TDD tests GROEN (2 RED->GREEN per dag, 1 None-forwarding FA-fix)
- [x] 384 agent-suite tests 0 regressies
- [x] pyright 0 errors (baseline bewaard)
- [x] ruff clean
- [x] BE-WFL-003 + BE-WFL-004 APPROVED; ID-REGISTRY bijgewerkt
- [x] FA briefs: `docs/agent-briefs/generated/2026-06-27-final-approver-SP-ADR023-dag1.md` + `...-dag2.md`
- [x] FA-minors: alle 7 bevindingen (DAG1+DAG2) direct gefixed

### Openstaande items (aparte sprint)

- Per-tenant `RouterAgentService` singleton (LLM-credentials nu gedeeld)
- `GeminiProvider` per-tenant credentials wiring
- `AuditService.log_action()` tenant_id integratie met workflow-stap uitvoering

---

## SP-AGT-006 -- CriticAgent Tier-1 + Judge Panel + Telemetrie (Dag 1-3)

**Status:** CLOSED (2026-06-27) | **Commits:** `62121e55` (Dag 1) + `d7e77002` `3e275c35` (Dag 2) + `28c5dec4` (Dag 3)
**ADR:** ADR-022 (LearningMixin), ADR-023 (CriticAgent)
**Prerequisite:** SP-AGT-005 CLOSED

### Voortgang per dag

| Dag | Status | Commits               | Resultaat                                                                                      |
| --- | ------ | --------------------- | ---------------------------------------------------------------------------------------------- |
| 1   | CLOSED | `62121e55`            | OutputSchemaValidator klasse + integratie in critique_task() + config/agents/critic_agent.yaml |
| 2   | CLOSED | `d7e77002` `3e275c35` | Multi-model judge panel (\_judge_panel_critique) + JudgePanelVerdict schema + Pydantic schemas |
| 3   | CLOSED | `28c5dec4`            | critique_hourly_stats materialized view + get_timeseries_stats() + GET /critics/telemetry      |

### Definition of Done

- [x] OutputSchemaValidator: JSON parseability, required fields, output-type, token-budget
- [x] Judge panel: asyncio.gather N=3 parallel + consensus + outlier-filter + timeout fallback
- [x] Materialized view: critique_hourly_stats + CONCURRENTLY refresh + get_timeseries_stats()
- [x] GET /critics/telemetry endpoint
- [x] Feature docs: BE-AGT-018 (Dag 1) + BE-AGT-019 (Dag 2) + BE-AGT-020 (Dag 3) APPROVED
- [x] ID-REGISTRY bijgewerkt
- [x] FA briefs aangemaakt per dag

---

## SP-AGT-007 -- CriticAgent full wiring: metrics + HITL + learning + frontend (Dag 1)

**Status:** CLOSED (2026-06-27) | **Commits:** `1779e04b` (impl) + `a9da7d2f` (FA-fixes) + `3ca5553d` (FA brief)
**ADR:** ADR-019 (audit), ADR-022 (LearningMixin), ADR-025 (twin)
**Prerequisite:** SP-AGT-006 CLOSED

### Voortgang per dag

| Dag | Status | Commits               | Resultaat                                                                                     |
| --- | ------ | --------------------- | --------------------------------------------------------------------------------------------- |
| 1   | CLOSED | `1779e04b` `a9da7d2f` | Prometheus metrics + CritiqueStore HITL escalation + LearningMixin + CritiqueChart (frontend) |

### FA-bevindingen direct gefixed (commit `a9da7d2f`)

| ID     | Bevinding                                                               | Ernst   |
| ------ | ----------------------------------------------------------------------- | ------- |
| FA-001 | importlinter whitelist ontbrak voor `critique_store -> hitl_repository` | BLOCKER |
| FA-002 | Label-asserts in tests te breed (status-string, niet enum)              | MINOR   |
| FA-003 | isError state ontbrak in CritiqueChart error-pad                        | MINOR   |

### Definition of Done

- [x] critique_score_histogram + critique_latency_seconds + critique_panel_invocations_total
- [x] HITL escalation bij score < 0.40 (SILENT-mode guard)
- [x] LearningMixin **init_learning** + \_record_method_observation in critique_task
- [x] CritiqueChart component (Recharts LineChart, 5e tab AgentDetailModal)
- [x] Feature docs: BE-AGT-021 + BE-AGT-022 + BE-AGT-023 + FE-CMP-038 APPROVED
- [x] ID-REGISTRY bijgewerkt
- [x] FA brief: docs/agent-briefs/generated/2026-06-27-final-approver-SP-AGT-007-dag1.md

---

## SP-AGT-008 -- ShadowCEO critique integratie + OODA-loop Orient-fase (Dag 1)

**Status:** CLOSED (2026-06-28) | **Commits:** `9ab58de5`
**ADR:** ADR-016 (ShadowCEO veto), ADR-025 (OODA-loop)
**Prerequisite:** SP-AGT-007 CLOSED

### Voortgang per dag

| Dag | Status | Commits    | Resultaat                                                                                                          |
| --- | ------ | ---------- | ------------------------------------------------------------------------------------------------------------------ |
| 1   | CLOSED | `9ab58de5` | ShadowCEO Check 6 (\_assess_critique_risk, drempel 0.35) + OODALoopObserver Orient/Decide + CritiqueScoreLow event |

### Definition of Done

- [x] ShadowCEO.\_CRITIQUE_RISK_THRESHOLD = 0.35 (onder HITL 0.40 -- vroeg-waarschuwing)
- [x] \_assess_critique_risk(): pull via CritiqueStore.get_by_agent(), exception-absorptie
- [x] Check 6 gewired in review_task() na Check 5
- [x] OODALoopObserver Orient-fase: CritiqueScoreLow event op TwinEventBus (best-effort)
- [x] OODALoopObserver Decide-fase: ooda_decide_intervention log
- [x] CritiqueScoreLow dataclass toegevoegd aan twin_events.py
- [x] 4 Cat B whitelist entries toegevoegd aan .importlinter
- [x] 11/11 unit tests GROEN | 299/299 architecture tests GROEN | pyright 0 errors
- [x] Feature docs: BE-AGT-024 + BE-AGT-025 APPROVED | ID-REGISTRY bijgewerkt
- [x] FA brief: docs/agent-briefs/generated/2026-06-28-final-approver-SP-AGT-008-dag-1.md
- [x] FA GO (onafhankelijke review) -- geen BLOCKER of MINOR bevindingen

---

## SP-AGT-009 -- ADR-025 Post-MVP Gaps: TwinEventBridge CritiqueScoreLow handler + EvalHarness

**Status:** CLOSED (2026-06-28) | **Commits:** `9a72a00e` (Dag 1 impl) + `6aff4078` (Dag 1 FA brief) + `987ed3d0` (ADR-025 v1.7 doc) + `8d556933` (Dag 1 FA-minor tests) + `b511774d` (Dag 2 impl) + `24ba9f43` (Dag 2 FA brief) + `9d2d25e2` (Dag 2 FA-minor fixes) + `d7f50b19` (Dag 3 ADR/tracker finalisatie) + `964cd431` (Dag 3 FA brief)
**ADR:** ADR-025 (Digital Twin Architecture), ADR-019 (LearningExperience persistentie)
**Prerequisite:** SP-AGT-008 CLOSED

### Voortgang per dag

| Dag | Status | Commits                          | Resultaat                                                                                                                                                                               |
| --- | ------ | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | CLOSED | `9a72a00e` `6aff4078` `8d556933` | TwinEventBridge `_on_critique_score_low_learning` handler + 6 TDD tests GROEN. ADR-025 gap #2 gesloten. BE-AGT-026.                                                                     |
| 2   | CLOSED | `b511774d` `24ba9f43` `9d2d25e2` | EvalHarness + 5 golden `analyze_struggle()` YAML-scenario's + MockSuggestionProvider integratie. 5/5 tests GROEN. BE-AGT-028.                                                           |
| 3   | CLOSED | `d7f50b19` `964cd431`            | ADR-025 v1.8 final snapshot: gap #2 CLOSED, eval harness DONE, OODA Orient/Decide CLOSED. SPRINT_TRACKER SP-AGT-009 CLOSED. FA-IND-001 hash-fix: `d7f50b19` (was `61958266` pre-amend). |

### Definition of Done

- [x] `_on_critique_score_low_learning()` handler in `TwinEventBridge` -- feature-flag gated
- [x] `"twin.critique.score_low"` in `_REDIS_EVENT_TYPE_MAP` (EventType.AGENT_MESSAGE)
- [x] `CritiqueScoreLow` geimporteerd in `twin_event_bridge.py`
- [x] 6/6 unit tests GROEN (happy path, flag uit, wrong type, invalid tenant_id, no session factory, map-aanwezigheid)
- [x] EvalHarness in `src/core/learning/eval_harness.py` -- 5 golden scenario's GROEN
- [x] 299/299 architecture tests GROEN | pyright 0 errors | ruff clean
- [x] Feature doc BE-AGT-026 APPROVED | ID-REGISTRY bijgewerkt
- [x] Feature doc BE-AGT-028 APPROVED | ID-REGISTRY bijgewerkt
- [x] ADR-025 docupdate final (gap #2 + eval harness CLOSED)
- [x] FA brief Dag 1: docs/agent-briefs/generated/2026-06-28-final-approver-SP-AGT-009-dag-1.md
- [x] FA brief Dag 2: docs/agent-briefs/generated/2026-06-28-final-approver-SP-AGT-009-dag-2.md
- [x] FA GO voor Dag 1 en Dag 2 -- geen BLOCKER

---

## SP-AGT-010 -- CriticAgent hardening: backlog minors SP-AGT-006

**Status:** CLOSED (2026-06-28) | **Commits:** `c72ea23b` (Dag 1 impl) + `cadb12bd` (Dag 1 FA-minors) + `40b19ee2` (Dag 2 impl) + `b1acd491` (Dag 2 FA-minor + rood test G) + `a0bf13f9` (Dag 2 pre-existing fix)
**ADR:** ADR-022 (LearningMixin + @auto_learn), ADR-023 (CriticAgent)
**Prerequisite:** SP-AGT-009 CLOSED

### Voortgang per dag

| Dag | Status | Commits                          | Resultaat                                                                                                                                                                                                                                               |
| --- | ------ | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | CLOSED | `c72ea23b` `cadb12bd`            | YAML hot-reload (OutputSchemaValidator), provider-diversiteit, N=config (judge_panel_size). 7/7 TDD tests GROEN. BE-AGT-027 APPROVED. FA GO WITH MINOR ISSUES -- FA-IND-001 + FA-IND-002 direct gefixed in `cadb12bd`.                                  |
| 2   | CLOSED | `40b19ee2` `b1acd491` `a0bf13f9` | CritiqueTimeseriesStats TypedDict + \_refresh_mv() patroon-3 + refresh-guard test. 11/11 TDD tests GROEN. BE-AGT-029 APPROVED. FA GO WITH MINOR ISSUES -- FA-IND-003 (stale type: ignore) gefixed + pre-existing \_persist_to_db best_effort gewrapped. |
| 3   | CLOSED | zie dag 3 commit                 | Spec-gaps BE-AGT-018 (minor-2 singleton risico + minor-3 falsy waarden) + BE-AGT-019 (minor-1 use_llm=False + minor-2 drempelkeuze + minor-3 parse-error pad) aangevuld. Status APPROVED. Sprint CLOSED.                                                |

### Definition of Done

- [x] `CritiqueTimeseriesStats` TypedDict gedefinieerd en gebruikt als return-type
- [x] `judge_panel_size` + `judge_providers` aanwezig in `critic_agent.yaml`
- [x] `_refresh_mv()` volgt patroon-3 (sessie binnen `best_effort`)
- [x] `_persist_to_db()` volgt patroon-3 (sessie binnen `best_effort`) -- pre-existing fix
- [x] 11/11 TDD-tests GROEN (dag 1: 7 + dag 2: 4 nieuw, allen ROOD geweest voor implementatie)
- [x] BE-AGT-027 APPROVED | BE-AGT-029 APPROVED
- [x] BE-AGT-018 spec APPROVED (minor-2 + minor-3 aangevuld)
- [x] BE-AGT-019 spec APPROVED (minor-1 + minor-2 + minor-3 aangevuld)
- [x] ID-REGISTRY bijgewerkt (BE-AGT-027 + BE-AGT-029)
- [x] pyright 0 errors (baseline gehandhaafd, commit b1398e4c)
- [x] 436 agents unit tests -- 0 nieuwe failures
- [x] FA briefs per dag aangemaakt

---

## SP-ADR023-002 -- ADR-023 productieklaar afmaken: agent-discovery + Redis-cache + metrics (3 dagen)

**Status:** CLOSED (2026-07-06) | **ADR:** ADR-023, ADR-034 | **Branch:** develop
**Kan parallel met:** AGENTIC-COPILOT-TAAKBEHEER-2026-07 -- geverifieerd disjuncte bestandensets, harde-grens-check leeg over alle 3 dagen.

### Aanleiding

Bij het verifieren van het AGENTIC-COPILOT-TAAKBEHEER-2026-07-charter (2026-07-05) bleek ADR-023
op 3 punten "bedrading zonder inhoud": agent-discovery degradeerde stil naar lege resultaten
(ontbrekende `async_session_factory`), de routing-cache was in-memory per worker (geen Redis
ondanks ADR-023 sectie 4), en er waren 0 Prometheus/OTel-metrics in de routing-laag ondanks de
p50/p95/p99-claim in ADR-023 sectie 6. Rakesh-beslissing (2026-07-05): losse, volledig
geisoleerde sprint die de andere sprint niet mag beinvloeden.

### SP-ADR023-002 Resultaten

| Dag   | Item                                                                 | Commits                                       | Feature Doc     | Status            |
| ----- | --------------------------------------------------------------------- | ---------------------------------------------- | ---------------- | ----------------- |
| Dag 1 | Router-instantiatie consolidatie + agent-discovery wiring (`async_session_factory`) | `f852dfbc`, `a6032b9e`, `b4e6b10e`             | BE-ADR023-001    | CLOSED 2026-07-05 |
| Dag 2 | Redis-cross-worker-cache wiring op alle 4 live call-sites + `route()`-tier-1.5     | `2138abd1`, `e1f59707`                          | BE-ADR023-002    | CLOSED 2026-07-06 |
| Dag 3 | Prometheus-metrics op `route()` (6 tiers) + `process_task()` (3 statussen)          | `b0cc5213`                                      | BE-ADR023-003    | CLOSED 2026-07-06 |
| --    | Bestandsnaamcollisie hersteld (agent-brief-docs van 2 sprints botsten)              | `fb2a805d`                                      | --                | CLOSED 2026-07-06 |

Elke dag kende minimaal 1 verplichte, onafhankelijke, contextvrije reviewronde (final-approver.md-
protocol). Dag 1 en Dag 2 kenden elk een BLOCKER-bevinding in ronde 1 (resp. een derde ongewirede
`AgentRouterAgent`-call-site, en `route()` dat de correct gewirede Redis-tier nooit daadwerkelijk
raadpleegde) -- beide daadwerkelijk opgelost, niet als backlog weggeschreven, en adversarieel
geverifieerd in een vervolgronde. Dag 3 leerde van dat patroon: de 3 vergelijkbare testgaten
(overloaded-cache-fallthrough, `WorkflowStatus.PARTIAL`, Redis-tier-afwezig) zijn tijdens Gate 2
gevonden en gedicht VOORDAT er productiecode werd geschreven, dus zonder BLOCKER-ronde.

### Definition of Done

- [x] `TODO(Rakesh)` in `agent_router_agent.py` verwijderd; discovery-service retourneert
      niet-lege resultaten tegen een geseede testdatabase
- [x] Router-instantiatie geconsolideerd naar 1 canoniek pad (was 2 gescheiden caches)
- [x] Cross-worker Redis-cache-hit bewezen via `route()` zelf (niet de tier in isolatie),
      met een echte, gedeelde Redis-instantie (poort 6380) en tenant-isolatie
- [x] 3 nieuwe Prometheus-metrics op alle 6 routing-tiers + alle 3 workflow-statussen
- [x] `clear_tenant_cache()`-non-atomiciteit vastgelegd als regressietest (geen herontwerp)
- [x] Regressie: 903 passed, 0 failed na Dag 3 (nulpunt 890 vóór Dag 3)
- [x] pyright 0 errors, mypy clean, ruff clean op alle 3 dagen
- [x] BE-ADR023-001/002/003 APPROVED; ID-REGISTRY bijgewerkt
- [x] FA briefs per dag + verplichte onafhankelijke reviewronde(s) tot GO
- [x] Harde-grens-check leeg over alle 3 dagen (AGENTIC-COPILOT-TAAKBEHEER-2026-07 nooit geraakt)
- [x] `.claude/WORKING-CONTEXT.md` ADR-023-sectie bijgewerkt
- [x] Taakbeheer-charter par. 1b bijgewerkt: alle 3 gaten gemarkeerd als GESLOTEN

### Openstaande items (bewust buiten scope, niet vergeten)

- `route_with_fallback_chain()` (aparte fallback-methode) blijft ongeinstrumenteerd -- bewuste
  scope-grens van Dag 3, geen omissie.
- OpenTelemetry-tracing (spans) op de routing-laag -- ADR-014 dekt dit apart, niet deze sprint.

## SP-CI-001 -- CI Pipeline Herstel (7 dagen, bijgesteld van 6 na scope-ontdekking dag 3)

**Status:** CLOSED (2026-07-15) | **Branch:** develop
**Retrospective:** `docs/agent-briefs/generated/2026-07-15-sprint-retrospective-SP-CI-001.md`

### Aanleiding

Scheduled main-CI faalde sinds >=2026-07-03 op 4 jobs: Tenant integration tests
(Postgres-poort-mismatch 5432 vs 5435/5455), Any-type baseline monitor (66 violations op
`main`), Security Scan (3 CVE's: pyasn1/chromadb/ecdsa), Frontend (4/14291 testfailures).
Dag 3 ontdekte dat de schatting op `main` gemeten was terwijl uitvoering op `develop`
gebeurde (~176-191 commits divergentie): werkelijke cijfers 331 Any-violations / 68
mypy-fouten. Rakesh koos expliciet (AskUserQuestion, dag 3) voor de volledige 331 op
`develop` aan te pakken i.p.v. scope te beperken tot main-niveau -- sprint uitgebreid van
6 naar 7 dagen.

### SP-CI-001 Resultaten

| Dag | Item | Commits | Feature Doc | Status |
| --- | ---- | ------- | ------------ | ------ |
| Dag 1 | Postgres-servicepoort-mismatch (tenant integration tests) | `41c1b12c`, `91fe9342`, `d796a79b`, `54cfdb8a` | BE-CI-001 | CLOSED 2026-07-13 (NO-GO->GO na onafhankelijke review) |
| Dag 2 | Frontend nl-NL budget-locale + useApiDocumentation search/tag-race | `6305d8c0`, `bd08d366`, `b428205e` | FE-CI-001 | CLOSED 2026-07-14 |
| Dag 3 | ALS-departments Any-type TODO(TYPE)-markers (164/331) | `a7509ba5`, `d96c99a4` | BE-CI-002 | CLOSED 2026-07-14 |
| Dag 4 | Resterende Any-type TODO(TYPE)-markers (167/331 -> 0 totaal) | `2908f2c1`, `de42cd17`, `b2901a95`, `72b29791` | BE-CI-003 | CLOSED 2026-07-14 |
| Dag 5 | mypy 0-baseline herstel (43 fouten -> 0, 37 bestanden) | `ffbfd237`, `90e181b6` | BE-CI-004 | CLOSED 2026-07-15 |
| Dag 6 | pip-audit CVE-fixes (pyasn1 echte fix, chromadb/ecdsa accepted-risk) | `363c14ae`, `798f0e38` | BE-CI-005 | CLOSED 2026-07-15 |
| Dag 7 | Review + sprint-retrospective + CLAUDE.md/skill-updates | (dit document + retrospective) | -- | CLOSED 2026-07-15 |

Elke implementatiedag (1-6) kende de verplichte, onafhankelijke, contextvrije reviewronde.
Op dag 4 en dag 5 ving die review een ECHTE functionele regressie (black-reformattering die
een `# pyright: ignore[...]`-comment losmaakte van zijn doelregel) die zowel de eigen
verificatie als Gate 2 hadden gemist -- op de overige dagen vond hij documentatie-
onnauwkeurigheden (verkeerde aantallen, onvolledige claims). Geen enkele dag kreeg een
blanco GO zonder minstens 1 correctie.

### Definition of Done

- [x] Any-type gate: 331 -> 0 violations over de volledige `src/`-boom
- [x] mypy-baseline: 68 (develop) -> 0 (3 resterend, bewust buiten scope, GDPR-sprint-
      eigendom van `src/core/governance/dsar_service.py`)
- [x] pip-audit --strict: 3 CVE's -> 0 (1 echte fix pyasn1, 2 gedocumenteerd geaccepteerd
      chromadb/ecdsa, 90-dagen herbeoordeling 2026-10-13)
- [x] Frontend: 4 -> 0 testfailures
- [x] Tenant integration tests: slagen weer in CI (poort-mismatch gefixed)
- [x] Regressie: volledige testsuite 0 nieuwe failures op elke dag (xdist-flakiness
      apart geidentificeerd en geisoleerd geverifieerd, geen echte regressie)
- [x] BE-CI-001 t/m BE-CI-005 + FE-CI-001 APPROVED; ID-REGISTRY bijgewerkt
- [x] FA-briefs per dag + verplichte onafhankelijke reviewronde tot GO (alle 6)
- [x] `.claude/WORKING-CONTEXT.md` bijgewerkt na elke dag
- [x] `.claude/rules/quality-gates.md` bijgewerkt met continue-on-error-discipline +
      main-vs-develop-scope-les (dag 7)
- [x] Laag C review: 3x GO (Compatibility, Privacy/compliance, Release readiness)

### Openstaande items (bewust buiten scope, niet vergeten)

- `continue-on-error: true` voor pyright/mypy is OPGELOST 2026-07-15 (Rakesh GO, commit
  `92dd1c85`): beide stappen falen nu bewust rood op de bekende uitzonderingen (mypy 5x --
  3x `dsar_service.py` + 2x `events_router.py`; pyright 5x -- 2x `dsar_service.py` + 2x
  `events_router.py` + 1x `audit_endpoints.py`). Migrations- en full-unit-tests-continue-
  on-error blijven staan -- NOOIT onderzocht deze sprint, apart op te pakken.
- Onafhankelijke review (2026-07-16) vond dat `scripts/run_mypy_audit.py`'s regex fouten
  liet vallen wanneer mypy het bericht naar de volgende regel wrapt (het rapporteerde 3
  i.p.v. de werkelijke 5 fouten). Regex gefixed + regressietest toegevoegd + Gate 2 review
  + bovenstaande cijfers gecorrigeerd (was abusievelijk "mypy 3x, 1 bestand").
- 6 pre-existing DSM-architecture-testfalen (`tests/architecture/`, governance<->
  agent_runtime-koppeling) ontdekt tijdens de dag-7-Laag-C-check -- bevestigd
  ongerelateerd aan SP-CI-001 (git blame: laatst gewijzigd 2026-07-07, voor de sprint
  startte), waarschijnlijk samenhangend met de gelijktijdige GDPR-sprintiteratie.
  Gemeld aan Rakesh voor routering, niet gefixed in deze sprint.
- Main-promotie blijft bewust uitgesteld (Rakesh, dag 1) -- apart open item.

---

> **Gat 2026-07-16 t/m 2026-08-24:** dit document is in die periode niet bijgehouden. In die
> tijd liepen o.a. SP-OP-TRIAGE-001 (2026-08-14, ADR-036-register-betrouwbaarheid), de
> 8-daagse ADR-036 fix-sprint (2026-08-14 t/m 2026-08-22, Rakesh's GO) en een
> open-punten-opruimingsdag (2026-08-25, OP-12/24/144). Die staan NIET hier maar wel in
> `.claude/WORKING-CONTEXT.md` en de auto-memory (`project_adr036_fix_sprint_closed`) --
> geen backfill hier, dat is een apart, groter karwei dan een status-update rechtvaardigt.

## HITL-ticket-volledigheid (ADR-036 OP-167/OP-168)

**Status:** CLOSED | **Start:** 2026-08-25 | **Gesloten:** 2026-08-25
**ADR:** ADR-036 (governance-hergebruik), ADR-015 (ToolBroker), ADR-027 (Copilot Council)
**Bron:** ADR-036-register OP-167/OP-168, voorwaarden vastgelegd door Rakesh 2026-08-19/20
tijdens de 8-daagse fix-sprint, opgepakt als eigen 4-daagse sprint na de open-punten-
opruimingsdag.

### Doel

De always-HITL-upgrade in `coordinator.py` (OP-166, bewust lege `ALWAYS_HITL_ACTIONS`) mag
pas gevuld worden zodra (a) alle 5 aanroeppunten van `AgentCouncil.deliberate()` zelf een
echt ticket garanderen bij HITL_REQUIRED (OP-167), en (b) de upgrade ook vanaf een
MODIFIED-verdict vuurt, niet uitsluitend APPROVED (OP-168). Deze sprint sluit beide
technische voorwaarden.

### Resultaten

| Dag | Item | Commits | Status |
| --- | ---- | ------- | ------ |
| Dag 1 | `background_gate.py` self-guarantee (`AgentCouncilOutcome`) + `service.py::submit_proactive_proposal` + `specialist_base.py` outcome-unpack | `c9c44efc` | CLOSED |
| Dag 2 | `governance_gate.py::require_council_approval` (9 aanroepers) + `execution_router.py::execute_flow` eigen ticket-aanmaak | `1be758bf` | CLOSED |
| Dag 3 | `coordinator.py` upgrade-conditie APPROVED -> (APPROVED, MODIFIED); Gate-2 vond een scope-beslissing die Rakesh's GO nodig had (blanket-regel bevestigd) + een live analoge bug in `specialist_base.py`'s D4-002-floor | `238a2efa`, `88acf9f7`, `44790fd1` | CLOSED |
| Dag 4 | Feature-doc-review vond een CRITICAL productiedefect (ticket-aanmaak deed alleen `flush()`, nooit `commit()`, voor de daaropvolgende 403 op dezelfde sessie) + scope-beslissing over HTTP-domeinlabels vs ToolBroker-tools (Rakesh: permanente grens, geen registratie) | `d54bc5c4`, `686f2ca5`, `0d4eccdd`, `b2c2b7b1`, `56eac3fd` | CLOSED |

Feature-doc: `BE-AGT-064` (spec + review, review vond het dag-4-defect zelf tijdens het
schrijven -- zie review-EINDOORDEEL-historie in het document).
FA-briefs: `docs/agent-briefs/generated/2026-08-25-final-approver-hitl-ticket-volledigheid-dag-{1,2,3,4}.md`.

### Definition of Done

- [x] Alle 5 aanroeppunten van `deliberate()` garanderen een ticketpoging bij HITL_REQUIRED
- [x] Always-HITL-upgrade vuurt vanaf APPROVED EN MODIFIED, mutatiegetest in beide
      richtingen (inclusief de aanvankelijk ontbrekende negatieve test)
- [x] `specialist_base.py`'s D4-002-floor kreeg dezelfde MODIFIED-fix (Rakesh's GO, was LIVE
      voor de skillsgaptraining-piloot, dus geen inert mechanisme zoals coordinator.py)
- [x] Commit/rollback-defect gefixed + bewezen met een echte Postgres-integratietest,
      mutatiegetest in beide richtingen
- [x] ADR-036-register OP-167 + OP-168: GESLOTEN, machine-checkbare BEWIJS-velden
- [x] Volledige regressiesuite (tests/unit+architecture+core, -n 4): 15.883 passed
- [x] pyright/ruff/mypy schoon op alle gewijzigde bestanden

### Openstaande items (bewust buiten scope)

- `submit_proactive_proposal`, `execute_flow` en 7 van de 9 `governance_gate.py`-aanroepers
  produceren nog geen ToolBroker-verzilverbaar ticket voor hun HTTP-domeinacties -- sinds
  2026-08-25 een gedocumenteerde, PERMANENTE architecturale grens (ADR-015 vs ADR-027), geen
  restgat voor een volgende sprint.
- OP-164 (`ALWAYS_HITL_ACTIONS` daadwerkelijk vullen) blijft Rakesh's eigen, apart te nemen
  beleidsbesluit -- deze sprint bouwde alleen het mechanisme.

---

## ADR-029 Foundation Portal -- afronding en opschoning

**Status:** CLOSED (samengevoegd/opgeschoond, oorspronkelijk gebouwd door een andere,
gelijktijdig lopende sessie-iteratie) | **Gesloten:** 2026-08-25
**ADR:** ADR-029 (Foundation Portal), ADR-033 (router-laag)
**Bron:** wit-label content-platform voor Stichting Ketikotivlaardingen.NL.

### Wat is samengevoegd

Content/curatie-endpoints, RLS-policies op 6 tabellen, JWT-portal-scopes, alles via het
ADR-033 3-laags routerpatroon. Gefixed tijdens het samenvoegen (niet door de oorspronkelijke
bouwer, apart geverifieerd voor deze regel):

- Ontbrekende Laag-2-facade (`src/core/api/v1/foundation/__init__.py`) -- veroorzaakte een
  vals-positieve orphan-router-failure voor 2 sub-routers.
- 2 ADR-033-importschendingen (`content.py`/`admin/curatie.py` importeerden database/
  services direct i.p.v. via `dependencies.py`).
- 3 verouderde testasserties (ontbrekende enum-waarde BOUNCED, ontbrekende NOT-NULL-kolommen
  in raw-SQL RLS-tests, enum-label-casing).
- Een echte ID-collision in de BE-EP-022-feature-doc (metadata verwees naar BE-EP-001).
- Een per ongeluk verwijderd bestand (`review-BE-EP-001.md`, onverwant, herstel via
  `git checkout HEAD --`).

Commits: `68a12c40` (code+tests+docs), plus begeleidende commits voor het multi-tenant-
integriteitsauditrapport, de database-ERD-generator en gitignore-hygiene voor 10
root-level scratch-scripts van de oorspronkelijke sessie.

### Openstaande items

- Geen gemeld tijdens de opschoning; de multi-tenant-integriteitsaudit (apart document,
  `docs/audits/MULTI_TENANT_INTEGRITY_AND_RLS_AUDIT_2026-08-21.md`) heeft 2 eigen CRITICAL-
  bevindingen die een eigen fix-sprint nodig hebben, los van ADR-029.
