# ADR 026: Digital Twin — Production Hardening Decisions

**Status**: Accepted
**Implementation Status**: ADR-026 hardening scope implemented; broader Digital Twin maturity roadmap remains open (verified 2026-05-24)
**Date**: 2026-05-23
**Author**: Audit pass (post-MVP)
**Supersedes**: nothing (extends ADR-025)
**Related**: ADR-005 (Tenant RLS), ADR-014 (Observability), ADR-015 (HITL gate), ADR-019 (Audit log), ADR-022 (LearningMixin), ADR-025 (Digital Twin Architecture)

---

## Context

ADR-025 captures the MVP architecture. The verification pass on 2026-05-19 and the maturity roadmap that followed identified three design decisions that are necessary for enterprise production but were left open by ADR-025. This ADR records the proposed direction for those three decisions so that engineering can start without re-litigating the architecture each sprint.

The three decisions are independent in implementation but share one property: each one is **invisible at MVP scale and catastrophic at enterprise scale**. A pilot tenant of five users cannot trigger them; a Fortune-500 tenant with five thousand users will trigger all three within a week.

This ADR records and hardens only the failover/cost-governance, granular-consent, retention-scheduling, and async-delete decisions. It does **not** claim completion of the wider Digital Twin maturity roadmap from the implementation plan; items such as intervention-event publication, twin-specific health/observability modules, policy wiring, output sanitization, dedicated admin UI, and memory-domain sync remain outside this ADR's implementation scope.

This ADR covers:

1. LLM provider failover chain and cost governance
2. Granular consent model under AVG Art. 7 and Art. 22
3. Retention enforcement (the `expires_at` column from ADR-025 is currently a dead field)

---

## 1. LLM Provider Failover Chain and Cost Governance

### 1.1 Problem

ADR-025 §5 selects an LLM provider **once at service boot** via env-var priority. If `ANTHROPIC_API_KEY` is set, every request goes to Anthropic for the lifetime of the worker. Three failure modes follow:

- **Provider outage** — Anthropic returns 503 for 30 minutes; every Twin suggestion fails for 30 minutes. No automatic fallback to Gemini or Ollama.
- **Cost explosion** — a tenant in deep struggle (refactor week, bad deploy day) can trigger thousands of `analyze_struggle` calls. At Claude-3.5-Sonnet pricing this hits four-figure euro within hours, billed to our account.
- **Data residency drift** — for EU-only tenants we want to force Ollama, but the boot-time selection cannot adapt per tenant.

### 1.2 Decision

**1.2.1 Runtime failover chain with circuit breaker.**

Replace boot-time selection with a per-request chain:

```text
[provider_1: primary]  →  [provider_2: secondary]  →  [provider_3: tertiary]  →  Mock
```

Each provider is wrapped in a circuit breaker (3 consecutive failures opens the breaker for 60 seconds). On open breaker, the chain skips to the next provider. The default order is configurable per tenant via `tenant.llm_chain` JSON field.

Reference implementation outline:

```python
class FailoverLLMProvider(ILLMSuggestionProvider):
    def __init__(self, chain: list[ILLMSuggestionProvider]):
        self._chain = chain
        self._breakers = {p.id: CircuitBreaker(3, 60.0) for p in chain}

    async def suggest(self, context, profile) -> str:
        for provider in self._chain:
            if self._breakers[provider.id].is_open():
                continue
            try:
                result = await asyncio.wait_for(provider.suggest(context, profile), timeout=10.0)
                if result:
                    self._breakers[provider.id].record_success()
                    return result
            except Exception:
                self._breakers[provider.id].record_failure()
        return ""  # fail-safe empty
```

**1.2.2 Per-tenant monthly LLM cost cap.**

Add a `tenant_llm_budget` row per (tenant_id, month) with `budget_eur_soft` and `budget_eur_hard`. Cost is tracked per suggestion via the `twin_suggestion_log` table (new). When monthly consumption exceeds the soft cap, the chain skips paid providers and falls back to Ollama. When it exceeds the hard cap, the chain falls back to Mock.

The cost-per-call is computed from token counts returned by each provider (Anthropic and Gemini both expose `usage.input_tokens` and `usage.output_tokens`). For Ollama and Mock the cost is zero.

**1.2.3 EU-only mode forces Ollama-only chain.**

When a tenant's `data_residency` field is `eu-only`, the chain is forced to `[Ollama, Mock]` regardless of available API keys. This is enforced at chain-build time, not at request time, so there is no risk of a misrouted request.

The `data_residency` value is an explicit enum (`"global"` or `"eu-only"`) on the `tenants` table, set at tenant creation and editable by platform admins only. We explicitly reject inference from billing address, IP geo-location, or registration country: VPNs, cross-border entities, and billing-address mistakes create false negatives/positives that expose us to legal liability. The field defaults to `"global"` for all existing tenants.

### 1.3 Alternatives considered

- **Latency hedging** (fire two providers in parallel, take the first answer) — better latency, worse cost, conflicts with cost cap. Defer to Release 1.2.
- **Single primary with retry-only** — simpler, but does not address provider outage.
- **Tenant-scoped provider selection only** — does not address outage scenario.

### 1.4 Consequences

- **Positive**: outage-resilient, cost-bounded, residency-correct.
- **Negative**: more state to manage (circuit-breaker state per worker — must be Redis-backed if we want it shared across workers; otherwise each worker independently learns the breaker is open). Decision: start with per-worker breakers (no shared state), accept that during a real outage some workers will continue probing for up to 60s after others have given up.
- **Operational**: requires Prometheus counters `twin_llm_provider_failures_total{provider}`, `twin_llm_provider_circuit_open_total{provider}`, `twin_llm_cost_eur_total{tenant_id}`. Alert when `twin_llm_cost_eur_total > 0.8 * budget_eur_hard`.

---

## 2. Granular Consent Model (AVG Art. 7 + Art. 22)

### 2.1 Problem

The current consent model from ADR-025 §6 is three states (`enabled`, `paused`, `disabled`) applied uniformly to all Twin data processing. AVG Art. 7 requires that consent be **specific** to a purpose: the user must be able to allow behavior tracking without also allowing AI suggestions, or vice versa. Art. 22 grants users the right to opt out of solely automated decision-making.

Today, a user who wants to share behavior data for personalized greetings but does not want AI-generated interventions has no way to express that. Their only options are "all on" or "all off".

### 2.2 Decision

Replace the single `consent_given` boolean with **four boolean consent categories** plus the existing state machine:

| Category | Default | Purpose | AVG basis |
|---|---|---|---|
| `behavior_tracking` | true | Persist anonymized observations to `user_behavior_observations` | Art. 6(1)(f) legitimate interest + Art. 7 consent |
| `profile_aggregation` | true | Build and maintain `user_cognitive_profile` from observations | Art. 6(1)(f) + Art. 7 |
| `ai_interventions` | true | Generate LLM suggestions on struggle detection | Art. 7 + Art. 22 (right to object to automated decision-making) |
| `cross_session_memory` | true | Profile persists across sessions instead of being session-scoped | Art. 7 |

The `UserTwinConsent` table gains four boolean columns; the existing `consent_given` is kept for backward compatibility and mirrors `behavior_tracking AND profile_aggregation AND ai_interventions AND cross_session_memory`.

The state machine from ADR-025 §6 (`enabled` / `paused` / `disabled`) becomes a **convenience layer on top**: `enabled` = all four true, `disabled` = all four false, `paused` = `behavior_tracking=false` but profile + memory retained.

A new endpoint replaces the two existing ones:

```http
PATCH /api/v1/learning/twin/consent
Content-Type: application/json
{
  "behavior_tracking": true,
  "profile_aggregation": true,
  "ai_interventions": false,   // user wants tracking but no AI suggestions
  "cross_session_memory": true
}
```

The legacy `PUT /twin/consent` with `{"status": "enabled"}` continues to work and maps to the four-boolean shape.

### 2.3 Frontend impact

`DigitalTwinSettingsPage` gains four toggles in place of one switch, each with a one-line description from a translation file (i18n is a separate work item from §3 of the maturity roadmap). The previous "enable / disable" button is shown as a quick-action that flips all four at once.

**Geimplementeerd in SP-FE-2G (Dag 1+3, 2026-06-29):**

| Component | Bestand | Status |
| --- | --- | --- |
| `ConsentToggle` component | `frontend/src/components/twin/ConsentToggle.tsx` | Geimplementeerd (FE-CMP-041) |
| `useDigitalTwinProfile` hook | `frontend/src/hooks/useDigitalTwinProfile.ts` | Geimplementeerd |
| Consent gate in `DigitalTwin.tsx` | `frontend/src/pages/DigitalTwin.tsx` | Geimplementeerd |

`ConsentToggle` implementeert de overall enable/disable toggle met pending state (AVG Art. 7 onboarding-vereiste -- klik-diepte max 1). De vier granulaire boolean toggles (`behavior_tracking`, `profile_aggregation`, `ai_interventions`, `cross_session_memory`) zijn frontend-TODO voor een volgende sprint; de PATCH-endpoint ondersteunt ze al.

De consent gate in `DigitalTwin.tsx` (ADR-026 §2.3) verbergt het twin-profile-card wanneer `consentQuery.data?.status !== 'active'`. OODATimeline, GDPRConsentPanel en portability-card blijven altijd zichtbaar ongeacht consent-status.

### 2.4 Alternatives considered

- **Single consent string with role-based templates** ("basic", "advanced", "off") — easier UI but does not satisfy Art. 7 specificity requirement.
- **Per-behavior-type consent** (consent per `behavior_type` value) — too granular, would force users to make choices about implementation details they do not understand.

### 2.5 Consequences

- **Positive**: AVG-compliant, gives users control, opens up future categories (e.g., "share aggregated stats with tenant admin") without further schema changes if we use a JSONB consent map instead of four booleans.
- **Negative**: every Twin pipeline gate must consult the relevant category, not just `consent_given`. Three new checks: observer reads `behavior_tracking`, aggregator reads `profile_aggregation`, struggle analyzer reads `ai_interventions`.
- **Migration**: existing consent rows have `consent_given` set. The migration sets all four new columns to that same value, so behavior is unchanged at deploy.

---

## 3. Retention Enforcement

### 3.1 Problem

ADR-025 §7 documents a 90-day retention policy and includes an `expires_at` column on `UserBehaviorObservation`. The verification pass on 2026-05-19 confirmed:

- The column exists in the migration `20260519_create_digital_twin_tables.py`.
- No code path writes to it on insert (`grep "expires_at" src/core/learning/repositories/` → 0 hits).
- No job deletes records based on it.

So the column is decorative. AVG Art. 5(1)(e) (storage limitation) is not enforced. A tenant audit would catch this in five minutes.

### 3.2 Decision

**3.2.1 Insert-time `expires_at` population.**

Update `insert_observation_batch()` to set `expires_at = created_at + TWIN_RETENTION_DAYS` on every insert, where `TWIN_RETENTION_DAYS` is a config var (default 90, range 4-365, configurable per tenant in Release 1.1).

**3.2.2 Daily cleanup Dramatiq actor.**

```python
@dramatiq.actor(queue_name="maintenance", max_retries=3, time_limit=10 * 60 * 1000)
async def twin_retention_cleanup() -> None:
    async with db.session() as s:
        result = await s.execute(
            delete(UserBehaviorObservation)
            .where(UserBehaviorObservation.expires_at < func.now())
            .returning(UserBehaviorObservation.id)
        )
        deleted = len(result.fetchall())
        logger.info("twin_retention_cleanup_done", deleted=deleted)
```

Scheduled by APScheduler at 03:00 UTC daily. The actor logs the number of deleted rows; alert if `deleted == 0` for seven consecutive days (indicates schema drift or stuck job).

**3.2.3 Profile-aggregator scheduling (also missing).**

ADR-025 §4 describes the aggregator design but does not specify the scheduling. The maturity-roadmap verification found that `profile_aggregator.py` exists but has no Dramatiq actor and no APScheduler trigger. Decision:

```python
@dramatiq.actor(queue_name="maintenance", max_retries=3, time_limit=30 * 60 * 1000)
async def twin_profile_aggregation_run() -> None:
    # Iterate tenants × users with observation activity since last_aggregated_at
    # Per-user isolation: one user failure does not stop the batch
    ...
```

Scheduled at 02:30 UTC daily (before the cleanup run so newly aggregated profiles do not get their source observations deleted in the same window).

**3.2.4 Hard-delete becomes async.**

The current `DELETE /twin/data` runs synchronously inside the request. For a user with 50k observations this can stall for tens of seconds. Decision: the endpoint sets `hard_delete_requested=True` (already supported by the schema) and enqueues a Dramatiq actor `twin_hard_delete_async(tenant_id, user_id)`. The endpoint returns immediately with 202 Accepted. The actor performs the cascade delete and logs to the audit log (ADR-019).

The actor must be idempotent: re-running it on an already-deleted user is a no-op.

The maximum time between user request and physical deletion is configurable. The default is 24 hours, which is defensible under GDPR Art. 17 "without undue delay" (most EU DPA guidance interprets this as "within one month at the absolute latest, but as fast as operationally feasible"). The 24-hour async design avoids stalling the API for users with large profiles. Platform operators can lower the global default via `TWIN_HARD_DELETE_MAX_HOURS`; tenant admins can request a stricter override via `tenant.twin_hard_delete_max_hours`, capped at 720 hours (30 days). The worker uses `min(global_config, tenant_config)` — the stricter of the two — preventing a tenant admin from relaxing the platform operator's setting.

**3.2.5 Cost log retention (7 years).**

The `twin_suggestion_log` table (created in Sprint 2, Taak 2.4) tracks per-suggestion cost data for fiscal audit compliance. Unlike `user_behavior_observations` (90 days under AVG Art. 5(1)(e)), cost logs must be retained for **7 years (2555 days)** per Dutch tax law (art. 52 AWR). A separate Dramatiq actor `twin_cost_log_retention_cleanup` runs daily at 03:15 UTC, 15 minutes after the observation cleanup. The two retention jobs are independent: a failure in one never blocks the other.

**3.2.6 Soft-delete zonder geplande hard-purge is per definitie non-compliant.**

Toevoeging 2026-07-29 (ADR-036 Fase A, AUDIT-004). Deze ADR dekt retentie en async hard-delete voor observaties en profielen, maar legde geen eis vast voor het Twin-geheugendomein (`memory_items` in `src/domains/memory/`). De audit bevestigde dat het dagspecifieke pad er wel degelijk was: `DSARService.execute_erasure()` markeerde memory-items alleen als soft-deleted (`deleted_at` gezet), en er bestond geen enkele actor of scheduler die die rijen fysiek verwijderde. Soft-deleted rijen met embeddings en persoonsgegevens bleven daardoor voor onbepaalde tijd in de database staan.

De volgende eis geldt vanaf heden voor **alle** Twin-data-verwijderpaden, niet alleen memory-items:

1. **Soft-delete zonder geplande hard-purge is non-compliant by definition.** Elke codepath die `deleted_at` zet op persoonsgegevens MOET vergezeld gaan van een geplande purge-actor met een expliciete grace period. Een soft-delete zonder purge is geen verwijdering in de zin van GDPR Art. 17.
2. **Embeddings zijn niet anonimiseerbaar.** Vector-embeddings kunnen persoonsgegevens reconstrueerbaar maken (embedding-inversion aanvallen). Anonimiseren of "vergeten via afscherming" is daarom onvoldoende; fysieke `DELETE` is vereist na afloop van de grace period.
3. **Grace period conventie**: 30 dagen (`MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS = 30`), tenzij een strengere tenant- of platformconfiguratie geldt. De per-tenant purge-regel wordt vastgelegd in de ADR-019 audit hash chain (`memory_purge_executed`).

Implementatie: BE-GDPR-003 (`src/domains/memory/services/memory_purge_service.py`, actor `purge_soft_deleted_memory_items` dagelijks 03:40 UTC, DSAR-hard-tak purget direct). Zie de formele ADR-036-update voor de programma-brede audit-context.

### 3.3 Alternatives considered

- **PostgreSQL native partitioning by `created_at` month** — best for very large tables, overkill for current scale, defer to when observations exceed 100M rows.
- **`pg_cron`** for the cleanup — simpler than Dramatiq but adds a new operational surface (a database-resident cron job). The existing Dramatiq + APScheduler combination (ADR-006, ADR-022) is the platform convention.

### 3.4 Consequences

- **Positive**: AVG Art. 5(1)(e) is now enforced. Observations age out automatically. Profile aggregator runs without manual intervention. Hard-delete no longer blocks the API.
- **Negative**: two new background jobs to monitor. Dead-letter queue must be wired with alerting.
- **Operational metrics**: `twin_retention_deleted_rows_total`, `twin_aggregation_users_processed_total`, `twin_hard_delete_pending_count`. Alert when `twin_hard_delete_pending_count > 100` (backlog growing).

---

## 4. Cross-cutting consequences of this ADR

If all three sections are implemented, the Twin gains:

- **Resilience** (no single LLM provider can take it down)
- **Cost predictability** (per-tenant budget cap)
- **Legal defensibility** (AVG Art. 5(1)(e) + Art. 7 + Art. 22 actively enforced)
- **Operational hygiene** (two scheduled jobs replacing manual data cleanup)

It also adds:

- One new table (`twin_suggestion_log` for cost tracking)
- One updated table (`UserTwinConsent` gains four columns)
- Two new Dramatiq actors (`twin_retention_cleanup`, `twin_profile_aggregation_run`, `twin_hard_delete_async`)
- New circuit-breaker state per worker (in-memory)
- Eight or nine new Prometheus counters/gauges (listed in §1.4, §3.4)

Total implementation effort: roughly two engineering weeks for one engineer, or one week with two engineers in parallel (the three sections are independent).

---

## 5. Open questions

Status per question after the 2026-05-19 product walkthrough with Rakesh.

### 5.1 Resolved (2026-05-19)

1. **Default opt-in vs. opt-out for `ai_interventions`** — **RESOLVED: opt-out (default true) with a mandatory onboarding experience requirement.**

    Rationale: Twin suggestions are hints, not decisions with legal effect or significant impact as defined in AVG Art. 22. The Twin therefore falls outside Art. 22's strict regime. The information obligation under Art. 13 must be satisfied by an onboarding or equivalent first-run disclosure that explicitly states that AI suggestions are active and shows the one-click disable path.

   Implementation constraint: the disable toggle must be at most one click deep from any twin-UI surface. Burying it in nested menus would shift the design from "opt-out with disclosure" to a dark pattern and re-open AVG exposure.

   Lawful basis: Art. 6(1)(f) legitimate interest, supported by Art. 7 consent for the granular categories (see ADR-026 §2).

2. **EU-only mode trigger** — **RESOLVED: explicit `tenant.data_residency` enum.**

   Decision: the `data_residency` field on the `tenants` table is an explicit enum (`"global"` or `"eu-only"`), set at tenant creation and editable by platform admins only. No inference from billing address, IP, or registration country. Inference was rejected because VPNs, cross-border entities, and billing-address mistakes create false negatives/positives. The field is read at chain-build time (not request time) inside `FailoverLLMProvider` construction.

   Migration: `20260521_tenant_data_residency.py` adds `data_residency VARCHAR(16) NOT NULL DEFAULT 'global'` and `twin_hard_delete_max_hours INT NULL` to the `tenants` table.

3. **`twin_suggestion_log` retention** — **RESOLVED: 7 years, separate retention actor.**

   Decision: `twin_suggestion_log` (cost tracking) is retained for 7 years (2555 days) for fiscal-audit compliance (Dutch tax law art. 52 AWR). `user_behavior_observations` stays at 90 days (AVG Art. 5(1)(e)). Two separate Dramatiq actors, separate Prometheus counters. The cost-log retention actor is co-implemented with Taak 2.4 (table creation).

4. **Hard-delete grace period** — **RESOLVED: configurable 1–720h, default 24h, no recovery window.**

   Decision: the "grace period" is the maximum time between user request and physical deletion. Default 24 hours. Configurable per tenant via `TWIN_HARD_DELETE_MAX_HOURS` (global, 1–720) and `tenant.twin_hard_delete_max_hours` (override, nullable). The async worker uses `min(global, tenant)`. No separate soft-delete recovery window is offered — that would conflict with GDPR Art. 17 "right to erasure". The 24h default is defensible under "without undue delay" (most DPA guidance: within one month, as fast as feasible). Jurisdictions with stricter national law can lower the config.

### 5.2 Still open

_None. All four questions from the 2026-05-19 product walkthrough are resolved._

---

## 6. Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-05-19 | Audit pass | Initial proposal, three sections, four open questions |
| 0.2 | 2026-05-19 | Product walkthrough | §5.1 Q1 resolved (opt-out + onboarding modal); Q2/3/4 remain open |
| 0.3 | 2026-05-21 | Architecture review | §5.2 Q2/Q3/Q4 resolved; explicit `data_residency` flag, 7-year cost-log retention, configurable hard-delete grace period |


---

## 7. Implementation Status

| # | Component | Status | File |
|---|---|---|---|
| 1.2.1 | FailoverLLMProvider with circuit breaker | ✅ Implemented | `src/core/learning/interfaces/failover_llm_provider.py` |
| 1.2.2 | Per-tenant monthly LLM cost cap | ✅ Implemented | `src/core/learning/twin_models.py` (`TenantLLMBudget`) |
| 1.2.3 | EU-only mode forces Ollama-only chain | ✅ Implemented | `src/core/learning/services/twin_service_factory.py` |
| 2 | Granular consent (4 categories) | ✅ Implemented | `src/core/learning/consent/consent_manager.py` + PATCH endpoint |
| 3.2.1 | Insert-time `expires_at` population | ✅ Implemented | `src/core/learning/repositories/observation_repository.py` |
| 3.2.2 | Daily observation cleanup actor | ✅ Implemented | `src/core/learning/worker.py` (`cleanup_expired_observations`) |
| 3.2.3 | Profile-aggregator scheduling | ✅ Implemented | `src/workers/scheduler.py` (daily 02:30) |
| 3.2.4 | Async hard-delete | ✅ Implemented | `src/core/learning/worker.py` (`twin_hard_delete_async`) |
| 3.2.5 | Cost log retention actor (7 years) | ✅ Implemented | `src/core/learning/worker.py` (`twin_cost_log_retention_cleanup`) |
| — | Admin API for tenant LLM budget | ✅ Implemented | `src/core/api/admin_learning_endpoints.py` |
| — | Prometheus metrics (6 counters/gauges) | ✅ Implemented | `src/core/learning/metrics.py` |
| — | Grafana alert rules | ✅ Implemented | `monitoring/alert_rules.yml` |
| — | Centrale retentie-service twin-tabellen | ✅ Implemented | `src/core/governance/retention_cleanup.py` |
| 3.2.6 | Memory-item hard-purge (30-dagen grace, per-tenant audit) | ✅ Implemented | `src/domains/memory/services/memory_purge_service.py`, `src/domains/memory/tasks.py`, `src/workers/scheduler.py` (dagelijks 03:40 UTC) |

**Verificatie:** 2026-05-24. Alle ADR-026 hardening-items uit bovenstaande tabel zijn teruggevonden in de codebase. Dit betekent nadrukkelijk niet dat het volledige Digital Twin maturity-plan voltooid is: open roadmap-items uit ADR-025 en het implementatieplan blijven bestaan, waaronder intervention-event publicatie, twin-specifieke health/observability modules, output sanitization, policy wiring, memory sync en een dedicated admin UI. De eerdere post-review fixes blijven van kracht: tenant isolatie (`_enforce_tenant_access`), alert rule metric (`twin_llm_budget_hard_eur`), failed counter in aggregation job, audit log `best_effort` wrapper, circuit breaker lock-safe accessor (`get_circuit_states`), duplicate scheduling verwijderd, structured logging, TODOs opgeschoond.

---

## 8. Changelog (post-implementatie)

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.4 | 2026-05-23 | Engineering | Status Proposed -> Accepted. Implementatie van alle 4 hiaten + metrics + alert rules + admin API. |
| 0.5 | 2026-05-23 | Engineering | Post-acceptatie review fixes: tenant isolatie admin API, alert rule metric, failed counter, audit log best_effort, circuit breaker lock safety, duplicate scheduling, logging standards, TODOs. + behavioral tests admin budget. |
| 0.6 | 2026-06-29 | SP-FE-2G | Frontend implementatie: ConsentToggle (FE-CMP-041), useDigitalTwinProfile hook, ADR-026 consent gate in DigitalTwin.tsx. §2.3 bijgewerkt met geimplementeerde componenten en openstaande granulaire toggles. |
| 0.7 | 2026-07-29 | ADR-036 Fase A dag 3 | §3.2.6 toegevoegd: expliciete purge-eis (soft-delete zonder geplande hard-purge = non-compliant; embeddings niet anonimiseerbaar). Aanleiding AUDIT-004; implementatie BE-GDPR-003. |
