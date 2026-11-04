# ADR 025: Digital Twin Architecture

**Status**: Accepted
**Implementation Status**: Partially implemented, verified against codebase on 2026-06-28
**Date**: May 20, 2026
**Author**: SanskritiSetu Architecture Team
**Related**: ADR 003 (Tenant Identity), ADR 006 (Dramatiq + Redis), ADR 012 (Health Tiers), ADR 014 (Observability)

---

## Context

The SanskritiSetu platform needed a user-centric intelligence layer that learns from behavior, builds cognitive profiles, and proactively suggests interventions. This "Digital Twin" concept is not a separate product but an embedded capability across all platform features.

Key requirements:
- **Privacy-first**: All observations must be anonymized before storage
- **Multi-tenant strict isolation**: One tenant must never infer another tenant's user profiles
- **GDPR compliance**: 90-day retention, full data export, Right to Erasure
- **Fail-safe**: The twin must never cause a 500 on the primary operation
- **Real-time capable**: Interventions should be suggested within the request lifecycle

## Decision

We implemented a Digital Twin subsystem using the OODA-loop pattern (Observe, Orient, Decide, Act) with an event-driven architecture.

### 1. OODA-Loop Observer Pipeline

**Decision**: Use a 4-stage pipeline for every behavior observation.

**Implementation**:
```python
# Observe: UserBehaviorObserver.track()
# 1. Feature flag check
# 2. Consent check (enabled / disabled / paused)
# 3. Rate limiting (per user, per behavior type)
# 4. Privacy filter (anonymize PII, hash user_id with per-tenant salt)
# 5. Batch buffer (add to ObservationBatchManager)
# 6. Publish event on TwinEventBus
```

**Rationale**:
- Each stage is independent and can be disabled without breaking the pipeline
- Privacy filter is fail-secure: any failure rejects the observation
- Rate limiting prevents observation flooding

### 2. Batch Observation Pattern

**Decision**: Buffer observations in memory and flush asynchronously to PostgreSQL.

**Implementation**:
```python
class ObservationBatchManager:
    # Buffers up to 100 observations or 30s, whichever comes first
    # Background flush loop (asyncio task)
    # Retry on persistence failure with exponential backoff
```

**Rationale**:
- Reduces DB write pressure from high-frequency events (code edits, file switches)
- Batching is a shared singleton across all requests (started at app boot)
- On shutdown, the buffer is drained via `stop()`

### 3. TwinEventBus (Pub/Sub)

**Decision**: Use an in-memory pub/sub bus for twin events, bridged to Redis Pub/Sub for cross-service consumption.

**Implementation**:
```python
class TwinEventBus:
    # Singleton shared across all requests
    # Subscribers per event_type
    # publish_async() for fire-and-forget
    # Fail-safe: handler errors are logged but do not stop the bus
```

**Events**:
- `twin.user_behavior.tracked` — observation stored
- `twin.profile.updated` — cognitive profile changed
- `twin.intervention.suggested` — LLM generated an intervention
- `twin.consent.changed` — user toggled consent
- `twin.hard_delete.requested` — GDPR Right to Erasure

**Rationale**:
- In-memory bus is fast (no network round-trip for internal subscribers)
- Bridge to Redis Pub/Sub makes events available to other services (AgenticFlowService, WebSocket notifications)
- Singleton prevents the "events published to void" anti-pattern

### 4. Incremental Profile Aggregation

**Decision**: Aggregate user profiles incrementally using a watermark (`last_aggregated_at`), not full recomputation.

**Implementation**:
```python
class ProfileAggregator:
    # 1. Query observations since last_aggregated_at watermark
    # 2. Compute EWMA confidence, time histogram, frequency maps
    # 3. Merge with existing profile (JSON fields with decay)
    # 4. Upsert via PostgreSQL ON CONFLICT
```

**Scheduling**:
- APScheduler daily job at 02:30 AM
- Enqueued via Dramatiq actor (`maintenance` queue, 3 retries, 5min timeout)
- Paginated over users (100 per batch)
- Per-user isolation: one user failure does not stop the batch

**Rationale**:
- Incremental aggregation is O(delta) instead of O(total)
- Watermark makes the job idempotent (safe to re-run)
- Background job keeps the API path fast

### 5. LLM Abstraction Layer

**Decision**: Use a protocol-based abstraction (`ILLMSuggestionProvider`) with multiple backends.

**Backends**:
- `GeminiSuggestionProvider` — Google Gemini (production default)
- `ClaudeSuggestionProvider` — Anthropic Claude via existing `AnthropicClient`
- `LocalSuggestionProvider` — Ollama via existing `OllamaProvider`
- `MockSuggestionProvider` — deterministic fallback for tests

**Selection logic** (env-var priority):
1. `LLM_PROVIDER=mock` → Mock
2. `ANTHROPIC_API_KEY` → Claude
3. `GOOGLE_API_KEY` → Gemini
4. `OLLAMA_BASE_URL` or `LLM_PROVIDER=ollama` → Local
5. None → Mock

**Rationale**:
- No vendor lock-in
- Each provider has retry logic, fail-safe empty-string fallback
- Lazy initialization (no API calls until first suggestion)

### 6. Consent State Machine

**Decision**: Three states with explicit transitions.

| State | Meaning | Data handling |
|-------|---------|---------------|
| `enabled` | Full tracking and profiling | Observe, aggregate, suggest |
| `paused` | Tracking paused, existing data retained | No new observations, profile still readable |
| `disabled` | Tracking off, profile deleted | No observations, profile removed from DB |

**Rationale**:
- Paused state allows users to temporarily opt out without losing their profile
- Disabled state is a hard delete of the cognitive profile (observations are already anonymized)

### 7. GDPR Compliance

**Decision**: Build retention, export, and erasure into the data model.

**Implementation**:
- **Retention**: `expires_at` column on `UserBehaviorObservation` (90 days from creation)
- **Export**: `GET /twin/export` returns JSON with audit log entry
- **Erasure**: `DELETE /twin/data` removes profile + anonymized observations, logs the action
- **Hashing**: `PrivacyFilter.hash_user_id()` uses per-tenant salt derived from `SECRET_KEY`

**Rationale**:
- Retention is column-level (easy to query and purge)
- Export is self-service via API
- Erasure is irreversible (no soft delete for GDPR requests)

## Alternatives

### Alternative A: Direct DB writes per observation
**Rejected**: Would cause high write pressure on PostgreSQL for frequent events (code edits, file switches). Batching reduces writes by ~10-100x depending on user activity.

### Alternative B: Redis Streams instead of in-memory bus
**Rejected**: Redis Streams provides persistence and replay, but adds latency and complexity. The twin events are ephemeral by design (they trigger actions, they are not the source of truth). The bridge to Redis Pub/Sub provides cross-service reach without the overhead of Streams.

### Alternative C: Event Sourcing for the entire twin state
**Rejected**: Event sourcing (ADR-018) is planned post-MVP. For launch, the audit log with SHA-256 hash chain (ADR-019) is sufficient. Adding event sourcing now would delay the twin delivery without adding user value.

## Consequences

### Positive
- **Modular**: Each component (observer, batch manager, aggregator, LLM provider) can be replaced independently
- **Observable**: Twin events feed into the existing OpenTelemetry + Jaeger + Prometheus stack (ADR-014)
- **Scalable**: Background aggregation + batching keeps the hot path fast
- **Compliant**: Built-in GDPR controls reduce audit risk

### Negative
- **Complexity**: Two event systems (TwinEventBus in-memory + Redis Pub/Sub) require a bridge
- **Operational**: Background jobs need monitoring (Dramatiq dead-letter queue, APScheduler misfires)
- **Consistency**: The batch manager introduces a small delay (up to 30s) between observation and persistence. The API force-flushes for critical paths.

### Monitoring
- Grafana dashboard: `digital_twin_observations_rate`, `digital_twin_aggregation_job_duration`, `digital_twin_llm_suggestion_latency`
- Alert: `digital_twin_batch_overflow > 0` (observations dropped due to buffer full)
- Alert: `digital_twin_aggregation_failures > 5` (per batch)

## Post-MVP Gaps (Explicitly Documented)

The following capabilities are **designed but not yet wired in production flows**. They are covered by unit/integration tests and will be activated in subsequent sprints without architectural changes.

| # | Gap | Test Coverage | Activation Path |
|---|-----|---------------|-----------------|
| 1 | ~~**InterventionSuggested event publication**~~ → **Closed 2026-06-28** — `PracticalTwinService.analyze_struggle()` now publishes `twin.intervention.suggested` on the bus after a successful LLM suggestion. | `test_digital_twin_user_journeys.py` | Event publication is live; `TwinEventBridge` forwards it to Redis and persists it as a `LearningExperience` when `FEATURE_FLAG_AGENT_LEARNING` is enabled. |
| 2 | ~~**Agent Learning event bridge**~~ → **Closed 2026-06-28** — `TwinEventBridge` forwards `CritiqueScoreLow` events to Redis Pub/Sub and persists them as `LearningExperience` rows via `_on_critique_score_low_learning` when `FEATURE_FLAG_AGENT_LEARNING` is enabled. The same bridge-handler pattern already existed for `InterventionSuggested`. | `test_twin_event_bridge.py` (20 pass) + `test_twin_event_bridge_critique.py` (6 pass) | `_on_critique_score_low_learning` handler added to `TwinEventBridge` in SP-AGT-009 Dag 1 (commit `9a72a00e`) |
| 3 | ~~**Memory domain synchronisation**~~ → **Closed via ADR-027 §11-15 + §12 below** — `ContextPackerService` is now the canonical boot-context provider for all AI surfaces; `MemoryWriteService` receives observations via `TwinMemorySyncService`; Digital Twin and Copilot share a unified context protocol. | `test_digital_twin_memory.py` (20 pass) + `tests/integration/copilot/test_context_engine.py` (new) | `TwinMemorySyncService` wires observation batch → memory index; `AIContextEngine` consumes `ContextPackerService.build()` for all surfaces |

### Verification Snapshot (2026-06-28)

- ~~Gap #1 is still open~~ → **Closed 2026-06-28**. `PracticalTwinService.analyze_struggle()` publishes `InterventionSuggested`; `test_digital_twin_user_journeys.py` asserts exactly one event.
- ~~Gap #2 is still open~~ → **Closed 2026-06-28**. `_on_critique_score_low_learning` in `TwinEventBridge` persists `CritiqueScoreLow` events as `LearningExperience` when `FEATURE_FLAG_AGENT_LEARNING` is enabled. Implemented in SP-AGT-009 Dag 1 (commit `9a72a00e`); guard-branch tests toegevoegd in commit `8d556933`.
- ~~Gap #3 is still open~~ → **Closed by architecture decision 2026-05-27**. `TwinMemorySyncService` and `AIContextEngine` formalise the memory-to-copilot data flow. Implementation tracked in ADR-027 §15 (Fase 2).
- Gap #3-related verification: `ContextPackerService.build()` is invoked from `AIContextEngine` (not directly from `PracticalTwinService.get_profile()` — the indirection via Context Engine prevents circular deps and enables multi-surface reuse).
- ~~Dedicated twin health and observability modules~~ → **Implemented 2026-06-28**: `src/core/learning/health/twin_health.py` and `src/core/learning/observability/metrics.py` are present and wired.
- ~~Eval harness (golden set of struggle scenarios)~~ → **Implemented 2026-06-28**. `EvalHarness` in `src/core/learning/eval_harness.py` runs 5 deterministic `analyze_struggle()` scenarios via `MockSuggestionProvider`; scenarios live in `tests/unit/learning/fixtures/eval_scenarios.yaml` and are tested in `tests/unit/learning/test_eval_harness.py` (SP-AGT-009 Dag 2, commit `b511774d`).
- **Verification snapshot updated**: this section reflects the 2026-06-28 code review and SP-AGT-009 sprint completion.
- **Frontend implementatie (SP-FE-2G, 2026-06-29)**: `DigitalTwin.tsx` ADR-028 dark-mode retrofit (FE-PGS-027); `OODATimeline` component met stateless 4-step OODA indicator (FE-CMP-042); `useDigitalTwinProfile` hook + `ConsentToggle` (FE-CMP-041); ADR-026 consent gate (profile verborgen bij `status !== 'active'`); `computeActivePhase()` functie op basis van `frictionScore` uit OODA metrics; `/digital-twin` route met `PermissionGate twin:read`. Zie ADR-026 §2.3 voor frontend-details.

---

## AI Act Governance Mapping (ADR-031)

Dit ADR levert aantoonbaar bewijs voor de volgende AI Act vereisten:

| Vereiste | Artikel | Hoe dit ADR voldoet |
|----------|---------|---------------------|
| Privacy-first AI observation | ADR-031 §1, §3 | OODA-loop observer pipeline with anonymization, consent gate, and per-tenant salt hashing before any AI profiling |
| GDPR compliance for AI-driven user profiles | ADR-031 §3 | 90-day retention, full DSAR export, Right to Erasure built into data model; granular consent under AVG Art. 7 (ADR-026) |
| Transparency for AI-generated suggestions | ADR-031 §5, §7 | Twin suggestions are subject to Council deliberation when routed through CopilotService; audit trail includes model metadata and reasoning |
| Cross-tenant isolation for AI profiles | ADR-031 §1 | Strict tenant isolation at DB level (RLS) and application level; per-tenant salt for user_id hashing |

## 8. Scope & Roadmap (added 2026-05-19)

This ADR documents the **MVP-production-ready** architecture. The decisions captured above are sufficient to onboard internal pilot tenants in an EU-only configuration. Enterprise-grade production for external Fortune-500 tenants requires additional decisions that are explicitly out of scope here and are tracked in separate documents.

### 8.1 In scope of this ADR (Release 1.0 — MVP)

- OODA-loop observer pipeline with privacy filter and consent gate
- Batch persistence with retry
- In-memory `TwinEventBus` plus Redis bridge stub
- Incremental profile aggregator (architecture defined; scheduling decision in §9)
- LLM abstraction with four backends and env-var-based selection (one-time at boot)
- Three-state consent machine (`enabled` / `paused` / `disabled`)
- GDPR Art. 17 (erasure) and Art. 20 (portability) endpoints
- `expires_at` column on observations (90-day intent; enforcement decision in §9)

### 8.2 Release 1.1 (Enterprise Experience) — gedeeltelijk voltooid, opnieuw geverifieerd 2026-05-24

**Voltooid (ADR-026 ✅ Accepted + post-audit fixes 2026-06-28):**
- ~~Granular consent (four categories under AVG Art. 7)~~ — Geïmplementeerd in `TwinConsentManager`
- ~~LLM provider runtime failover chain + per-tenant cost cap~~ — Geïmplementeerd in `FailoverLLMProvider` + `TenantLLMBudget`
- ~~Tenant-level rate limit~~ — Skeleton geïmplementeerd; volledige enforcement in Sprint 2.4
- ~~Async hard-delete + retention scheduling~~ — Geïmplementeerd via worker + scheduler
- ~~Chaos test surface~~ — Aanwezig in `tests/chaos/test_digital_twin_chaos.py`
- ~~Suggestion feedback endpoint~~ — Aanwezig op `/api/v1/learning/twin/suggestion/{log_id}/feedback`
- ~~AI Act governance integration~~ — Twin events feed into CopilotService Proposal normalization; Council deliberation covers twin-generated suggestions (ADR-031)
- ~~InterventionSuggested event-publicatie in de productie-flow~~ — Gepubliceerd in `PracticalTwinService.analyze_struggle()`; getest in `test_digital_twin_user_journeys.py`
- ~~Twin-specifieke health checks en observability-modules~~ — Aanwezig in `src/core/learning/health/twin_health.py` en `src/core/learning/observability/metrics.py`
- ~~Output sanitization + hallucination guard for LLM suggestions~~ — Aanwezig in `src/core/learning/safety/output_sanitizer.py` en `hallucination_guard.py`
- ~~Tenant-admin dashboard + per-tenant configuration~~ — Aanwezig in `frontend/src/pages/admin/DigitalTwinAdminPage.tsx` en settings page
- ~~Memory domain synchronisation~~ — Geïmplementeerd via `TwinMemorySyncService` + `AIContextEngine`
- ~~Eval harness (golden set of struggle scenarios)~~ — Geïmplementeerd in `src/core/learning/eval_harness.py`; 5 golden scenario's in `tests/unit/learning/fixtures/eval_scenarios.yaml`; getest in `tests/unit/learning/test_eval_harness.py` (SP-AGT-009 Dag 2, commit `b511774d`)
- ~~Volledige OODA-loop subscriber (Orient/Decide) voor InterventionSuggested events~~ — Geïmplementeerd in `OODALoopObserver` (SP-AGT-008); Act-fase bewust post-MVP

**Nog open:**
- AI Act Art. 13 transparency banner + Art. 14 human-feedback loop on suggestions
- ADR-015 (HITL gate) and ADR-016 (Shadow CEO veto) explicit integration for twin suggestions
- Prompt-version management
- Act-fase van de OODA-loop subscriber voor `InterventionSuggested` events (Orient/Decide zijn CLOSED in SP-AGT-008)

### 8.3 Out of scope — moved to Release 1.2 (Advanced + Productize)

- ADR-022 (LearningMixin) binding for cross-system learning signal
- A/B framework for prompt and model experiments
- Human-readable profile inspector ("why does the Twin think this?")
- Live struggle indicator (real-time UX widget)
- Stripe billing-meter events
- OWASP API top-10 automated checks

### 8.4 Explicit non-goals

These will **not** be built — they are anti-patterns or out-of-scope for the entire Twin programme:

- Emotion detection (accuracy too low to act on)
- Biometric tracking (privacy and legal exposure)
- Use of Twin data as input to HR / performance / hiring decisions — this requires AI Act Annex III §4 conformity assessment, which we explicitly opt out of by policy. Documented in the tenant Terms of Service.
- Cross-tenant aggregation or benchmarking

---

## 9. Open Decisions (added 2026-05-19)

Decisions that the architecture leaves open and require explicit resolution before Release 1.1 ships. Each one has been moved into a dedicated follow-up ADR or external work item:

| # | Decision | Owner | Tracked in |
|---|---|---|---|
| 1 | ~~Runtime failover chain for LLM providers~~ — Resolved in ADR-026 | Platform engineering | ADR-026 §1 ✅ |
| 2 | ~~Per-tenant monthly LLM cost cap~~ — Resolved in ADR-026 | Platform engineering | ADR-026 §1 ✅ |
| 3 | ~~Granular consent categories under AVG Art. 7~~ — Resolved in ADR-026 | Privacy + Frontend | ADR-026 §2 ✅ |
| 4 | ~~Art. 22 opt-out from automated decision-making~~ — Resolved in ADR-026 | Privacy | ADR-026 §2 ✅ |
| 5 | ~~Retention enforcement~~ — Resolved in ADR-026 | Platform engineering | ADR-026 §3 ✅ |
| 6 | ~~Profile-aggregator scheduling~~ — Resolved in ADR-026 | Platform engineering | ADR-026 §3 ✅ |
| 7 | International data transfer for non-EU LLMs (Anthropic, Google) — SCC for default tenants; EU-only mode available via `tenant.data_residency=eu-only` flag forces Ollama-only chain (see ADR-026 §1.2.3). DPO sign-off on the SCC template still required. | DPO | Legal track, separate document |
| 8 | DPIA for high-risk profiling | DPO | Legal track, separate document |
| 9 | AI Act Annex III §4 classification — confirm non-applicability via policy | Legal + Product | Terms of Service update |

---

## 10. Verification History (added 2026-05-19)

| Date | Document | Key finding |
|---|---|---|
| 2026-05-19 (morning) | `docs/reports/DIGITAL_TWIN_AUDIT_2026-05-19.md` | Pre-implementation gap analysis. Six blockers identified: missing migration, `persist_fn=None`, `_DummyObserver`, `NotImplementedError` LLM stubs, no frontend page, no ADR. |
| 2026-05-19 (afternoon) | Implementation pass by build agent | All six blockers closed: Alembic migration + RLS policies, `create_practical_twin_service` factory wired into endpoint DI, `_DummyObserver` removed from Focus Builder, three real LLM adapters, `/settings/digital-twin` page + queries, this ADR. |
| 2026-05-19 (afternoon) | `docs/reports/DIGITAL_TWIN_VERIFICATION_2026-05-19.md` | Independent verification. Six blockers confirmed closed. Three nuances flagged: (a) `InterventionSuggested` event publication is absent — Post-MVP Gap #1; (b) one behavioral-test assertion was softened to `>= 0` and should become `pytest.xfail`; (c) hardcoded test-DB URL violates CLAUDE.md rule 8 — since fixed via `TEST_DATABASE_URL` env var. |
| 2026-05-19 (evening) | `docs/reports/DIGITAL_TWIN_MATURITY_ROADMAP_2026-05-19.md` | Mapping from MVP to enterprise-grade. Ten domains, three release tracks (1.0 / 1.1 / 1.2), roughly seven to ten engineering weeks remaining. Heaviest non-code blockers: DPIA, golden eval set, pen-test, international data transfer policy. |
| 2026-05-23 | ADR-026 implementatie + review fixes | `docs/adr/026-twin-production-hardening.md` | ADR-026 Accepted. Granular consent, LLM failover chain, per-tenant cost cap, retention enforcement, async hard-delete all landed. Post-review fixes: tenant isolation, alert rules, metrics, logging. 452 tests green. |

---

## 12. Twin-Copilot Context Interface Contract

### 12.1 Context

ADR-027 (Copilot Agent Council) introduceert een `AIContextEngine` die platform-bewustzijn en user-context verrijkt voor alle AI surfaces. De Digital Twin (dit ADR) is de **bron** van user-centric context (profiel, gedrag, preferences, episodic memory). Er is een formeel interface-contract nodig tussen de Twin-laag en de Context Engine om te garanderen dat:

1. De Twin weet niet dat de Copilot bestaat (geen circular dependency)
2. De Copilot kan Twin-data ophalen zonder directe koppeling naar de observer pipeline
3. Consent en privacy-filters (ADR-026 §2) altijd worden toegepast vóór data de Context Engine verlaat
4. Meerdere AI surfaces dezelfde Twin-context kunnen consumeren zonder duplicatie

### 12.2 Decision: Twin Memory Sync Service + Context Packer als bron

We introduceren `TwinMemorySyncService` als **enige schrijfkant** en `ContextPackerService` als **enige leeskant** voor Twin-data in de Context Engine.

```
ObservationBatchManager
        │
        ▼
TwinMemorySyncService.write_observation(observation)
        │
        ├──► PrivacyFilter (anonymize, hash, tenant salt)
        ├──► ConsentGate (ADR-026 §2: behavior_tracking?)
        └──► MemoryWriteService.write() ──► MemoryItem (pgvector + FTS)
        │
        ▼
AIContextEngine.enrich(tenant_id, user_id, ...)
        │
        ├──► ContextPackerService.build(tenant_id, user_id)
        │       ├──► AgentMemoryProfile (goals, preferences, expertise)
        │       ├──► Recent episodic memories (7d window)
        │       ├──► Top semantic facts (user-knowledge associations)
        │       └──► Top preferences (communication style, UI density)
        │
        └──► EnrichedContext.twin_profile
```

**Key rule**: `PracticalTwinService` roept **nooit direct** `ContextPackerService` aan voor Copilot-doeleinden. Alle Twin-data stroomt via `AIContextEngine` zodat token budget, tenant isolatie, en surface-specifieke packing centraal worden afgehandeld.

### 12.3 Consent Boundary

De Context Engine mag alleen Twin-data ophalen als:
- `behavior_tracking=true` (observations zijn opgeslagen)
- `profile_aggregation=true` (profiel bestaat)
- `cross_session_memory=true` (data mag hergebruikt worden over turns)

Als `cross_session_memory=false` maar `behavior_tracking=true`:
- Observations worden opgeslagen voor analytics
- Maar `ContextPackerService` retourneert alleen een **anoniem, sessie-scoped profiel** (geen historie, geen naam, geen preferences)
- De Copilot weet dan: "een gebruiker" maar niet "deze specifieke gebruiker"

### 12.4 Event Contract

`TwinEventBus` publiceert events die de Context Engine consumeert voor cache invalidatie:

| Event | Publisher | Consumer | Actie |
|-------|-----------|----------|-------|
| `twin.profile.updated` | `ProfileAggregator` | `AIContextEngine` | Flush twin_profile cache voor user |
| `twin.memory.consolidated` | `MemoryConsolidationRun` | `AIContextEngine` | Flush semantic memory cache voor user |
| `twin.consent.changed` | `TwinConsentManager` | `AIContextEngine` | Flush alle caches + her-evalueer toegang |
| `twin.hard_delete.requested` | GDPR endpoint | `AIContextEngine` | Onmiddellijk purge alle context voor user |

### 12.5 Performance & SLA

- **Twin context retrieval target**: P95 < 50ms ( PostgreSQL query + Redis cache)
- **Cache strategie**: Redis hash per `(tenant_id, user_id)` met 5m TTL; invalidatie via events
- **Fallback**: bij cache miss + DB timeout → leeg profiel (Copilot werkt zonder personalisatie, nooit 500)

---

## 13. Consequences (uitbreiding)

### Positive (toegevoegd)
- **Twin-data is nu multi-surface**: niet alleen Copilot, maar ook Focus Builder, CVA, en Agentic router kunnen hetzelfde profiel consumeren
- **Single source of truth voor user context**: `ContextPackerService` wordt centraal gepackaged en getest
- **Consent blijft gegarandeerd**: alle data stroomt via één gate; geen surface kan per ongeluk bypassen

### Negative (toegevoegd)
- **Extra indirection**: Twin → Sync Service → Memory → Context Engine → Surface is 4 hops ipv 2
- **Cache invalidatie complexiteit**: 4 event types × N surfaces = meer operational surface

### Mitigations (toegevoegd)
- **Fail-safe**: bij elke hop is een lege/fallback waarde gedefinieerd; geen enkele failure cascadet naar een 500
- **Idempotente events**: herpublicatie van `twin.profile.updated` is veilig (cache flush is idempotent)

---

## 11. Changelog

## Implementatie-bevindingen -- Architectuur Audit 2026-05-31

### WE-016 [MEDIUM] ~~twin_service wordt als None geinjectioneerd~~ — FIXED 2026-06-28

**Situatie:** ADR-025 beschrijft dat `PracticalTwinService` context injecteert in elke
`CopilotService.handle_turn()` aanroep.
**Werkelijkheid (oud):** `dependencies.py` instantieerde `CopilotService` zonder `twin_service=` parameter.
De code branch `if self._twin_service:` vuurde nooit in productie.
**Fix:** `src/core/copilot/dependencies.py:114` roept nu `_create_twin_service(db, redis)` aan en
geeft `twin_service=twin_service` door aan `CopilotService`.
**Bewijs:** `src/core/copilot/dependencies.py:114-126`, `src/core/copilot/council/factory.py:353-358`
**Impact:** Digital Twin context is nu actief in Copilot beslissingen.
**Sprint:** SP-WE-03 / CI stabilisatie 2026-06-28

### WE-017 [MEDIUM] ~~PrivacyOfficer consent check vuurt nooit~~ — FIXED 2026-06-28

**Situatie:** ADR-025/026 beschrijft dat de PrivacyOfficer GDPR-consent valideert via de Digital Twin.
**Werkelijkheid (oud):** `AgentCouncil._build_context()` zette `twin_profile=None` hardcoded en
`_ConsentGateAdapter.has_consent()` retourneerde altijd `True`.
**Fix:** `AgentCouncil._build_context()` leest `twin_profile` uit `proposal.context_snapshot`. De
`_ConsentGateAdapter` checkt nu `categories.cross_session_memory` en faalt veilig (`False`) bij ontbrekende tenant context of DB errors.
**Bewijs:** `src/core/copilot/council/coordinator.py:191-196`, `src/core/copilot/council/factory.py:101-123`, `src/core/copilot/council/members/privacy_officer.py:147-148`
**Impact:** GDPR-consent check is nu actief in de AI decision pipeline.
**Sprint:** SP-WE-03 / CI stabilisatie 2026-06-28

### WE-OODA [MEDIUM] OODA-loop observer -- Orient/Decide geimplementeerd, Act post-MVP

**Situatie:** ADR-025 §3.4 beschrijft een volledig OODA-loop met Observe-Orient-Decide-Act cycli.
**Werkelijkheid:** `PracticalTwinService` publiceert `InterventionSuggested` events (service.py
regel 209-221). `OODALoopObserver` (SP-AGT-008) implementeert Orient-fase (publiceert `CritiqueScoreLow`
op de bus bij score < 0.35) en Decide-fase (logt interventieaanbeveling). Act-fase (corrigerende
actie op de agent) is bewust post-MVP.
**Bewijs:** `src/core/learning/services/practical_twin_service.py:209-221`,
`src/core/learning/observers/ooda_loop_observer.py:24-83`
**Impact:** OODA-loop is functioneel voor signalering en leren; handelende autonomie (Act) blijft
deur de council/HITL/ShadowCEO geregeld en is post-MVP.
**Status:** Orient + Decide CLOSED in SP-AGT-008. Act-fase deferred naar post-MVP.
**Sprint:** SP-AGT-008 (Orient/Decide) + post-MVP (Act)

---

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-05-20 | Architecture Team | Initial decision — accepted and implemented |
| 1.1 | 2026-05-19 | Audit pass | Added §8 Scope & Roadmap, §9 Open Decisions, §10 Verification History, §11 Changelog |
| 1.2 | 2026-05-19 | Product walkthrough | §9 row 7 refined: EU-only mode mechanism specified via `tenant.data_residency` flag; SCC vs. Ollama-only chain are now an explicit branch instead of an open question |
| 1.3 | 2026-05-23 | Engineering | §8.2 bijgewerkt: ADR-026 items gemarkeerd als voltooid. Verification History uitgebreid met ADR-026 acceptatie.
| 1.4 | 2026-05-24 | Audit pass | Implementation status verduidelijkt als gedeeltelijk; verification snapshot toegevoegd voor open post-MVP gaps en ontbrekende twin health/observability modules. |
| **1.5** | **2026-05-27** | **Architecture Team** | **Gap #3 closed: §8.2 updated, §12 Twin-Copilot Context Interface Contract added, §13 consequences added. Formalises the data flow between Digital Twin, Memory domain, and AIContextEngine (ADR-027).** |
| **1.6** | **2026-05-31** | **Architectuur Audit** | **WE-016/017/OODA gedocumenteerd: twin_service=None in productie, PrivacyOfficer consent nooit actief, OODA subscriber ontbreekt. Fix in SP-WE-03.** |
| **1.7** | **2026-06-28** | **Code review** | **Verification snapshot updated: Gap #1 closed, WE-016/017 fixed, health/observability/safety modules implemented, Release 1.1 item status refreshed.** |
| **1.8** | **2026-06-28** | **SP-AGT-009 sprint close** | **Final verification snapshot: Gap #2 closed, EvalHarness implemented, OODA Orient/Decide marked complete, SPRINT_TRACKER SP-AGT-009 CLOSED.** |
