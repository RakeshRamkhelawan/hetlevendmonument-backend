"""
Twin observability metrics -- ADR-026 S.1.2.3 instrumentation.

All metrics use the singleton-safe _get_or_create_* wrappers from
src.core.observability.metrics to avoid duplicate registration on
test reloads (pytest reimports modules per worker).

Metrics:
    TWIN_INTERVENTION_TOTAL       -- suggestions fired per tenant
    TWIN_INTERVENTION_SCORE       -- WeightedStruggleScore distribution
    TWIN_OBSERVATION_BATCH_SIZE   -- observations flushed per batch
    TWIN_CONSENT_CHANGES_TOTAL    -- consent update events per category
    TWIN_HARD_DELETE_TOTAL        -- GDPR erasure completions (Art. 17)
    TWIN_LLM_SUGGESTION_LATENCY   -- end-to-end LLM call duration
    TWIN_SANITIZER_VIOLATIONS     -- OutputSanitizer violations detected
"""

from prometheus_client import Counter, Gauge, Histogram

from src.core.observability.metrics import (
    _get_or_create_counter,
    _get_or_create_gauge,
    _get_or_create_histogram,
)

# -- 1. Interventions ---------------------------------------------------------

TWIN_INTERVENTION_TOTAL: Counter = _get_or_create_counter(
    name="twin_intervention_total",
    description="Total struggle interventions suggested per tenant",
    labels=["tenant_id"],
)

TWIN_INTERVENTION_SCORE: Histogram = _get_or_create_histogram(
    name="twin_intervention_score",
    description="WeightedStruggleScore distribution at intervention time",
    labels=["tenant_id"],
)

# -- 2. Batch manager throughput -----------------------------------------------

TWIN_OBSERVATION_BATCH_SIZE: Histogram = _get_or_create_histogram(
    name="twin_observation_batch_size",
    description="Number of observations per flush batch",
    labels=[],
)

# -- 3. Consent lifecycle ------------------------------------------------------

TWIN_CONSENT_CHANGES_TOTAL: Counter = _get_or_create_counter(
    name="twin_consent_changes_total",
    description="Consent category updates (TWIN_CONSENT_CHANGED audit events)",
    labels=["tenant_id", "category"],
)

# -- 4. GDPR hard delete -------------------------------------------------------

TWIN_HARD_DELETE_TOTAL: Counter = _get_or_create_counter(
    name="twin_hard_delete_total",
    description="GDPR Art. 17 hard-delete completions",
    labels=["tenant_id", "status"],
)

# -- 5. LLM suggestion latency -------------------------------------------------

TWIN_LLM_SUGGESTION_LATENCY: Histogram = _get_or_create_histogram(
    name="twin_llm_suggestion_latency_seconds",
    description="End-to-end LLM suggestion latency in seconds",
    labels=["tenant_id", "provider"],
)

# -- 6. Output sanitizer -------------------------------------------------------

TWIN_SANITIZER_VIOLATIONS: Counter = _get_or_create_counter(
    name="twin_sanitizer_violations_total",
    description="OutputSanitizer pattern violations detected",
    labels=["tenant_id", "violation_type"],
)

# -- 7. Pending hard-delete queue size (gauge) ---------------------------------

TWIN_HARD_DELETE_PENDING: Gauge = _get_or_create_gauge(
    name="twin_hard_delete_pending_count_v2",
    description="Users with outstanding hard-delete requests",
    labels=["tenant_id"],
)


# -- Convenience helpers -------------------------------------------------------


def record_intervention(tenant_id: int, score: float) -> None:
    """Record a struggle intervention with its score."""
    tid = str(tenant_id)
    TWIN_INTERVENTION_TOTAL.labels(tenant_id=tid).inc()
    TWIN_INTERVENTION_SCORE.labels(tenant_id=tid).observe(score)


def record_batch_flush(batch_size: int) -> None:
    """Record the size of an observation batch flush."""
    TWIN_OBSERVATION_BATCH_SIZE.observe(float(batch_size))


def record_consent_change(tenant_id: int, category: str) -> None:
    """Increment consent-change counter for a specific category."""
    TWIN_CONSENT_CHANGES_TOTAL.labels(tenant_id=str(tenant_id), category=category).inc()


def record_hard_delete(tenant_id: int, *, success: bool) -> None:
    """Record a completed hard-delete attempt."""
    status = "success" if success else "error"
    TWIN_HARD_DELETE_TOTAL.labels(tenant_id=str(tenant_id), status=status).inc()


def record_llm_latency(tenant_id: int, provider: str, seconds: float) -> None:
    """Record LLM suggestion end-to-end latency."""
    TWIN_LLM_SUGGESTION_LATENCY.labels(
        tenant_id=str(tenant_id),
        provider=provider or "unknown",
    ).observe(seconds)


def record_sanitizer_violation(tenant_id: int, violation_type: str) -> None:
    """Increment sanitizer violation counter."""
    TWIN_SANITIZER_VIOLATIONS.labels(
        tenant_id=str(tenant_id),
        violation_type=violation_type or "unknown",
    ).inc()


def set_hard_delete_pending(tenant_id: int, count: int) -> None:
    """Set the pending hard-delete gauge for a tenant."""
    TWIN_HARD_DELETE_PENDING.labels(tenant_id=str(tenant_id)).set(float(count))
