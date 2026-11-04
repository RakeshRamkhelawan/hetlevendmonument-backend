"""
Pack Activation Metrics for Prometheus Monitoring

Business metrics for monitoring pack activation trends as part of
the Paperclip pipeline integration (Plan 3, Task 2).
"""

from src.core.monitoring.prometheus_metrics import get_or_create_counter, get_or_create_histogram

# =============================================================================
# PACK ACTIVATION METRICS
# =============================================================================

PACK_ACTIVATIONS_TOTAL = get_or_create_counter(
    "pack_activations_total",
    "Total number of pack activations",
    ["department_id", "pack_id", "trigger"],  # trigger: 'auto' or 'manual'
)

PACK_ALIGNMENT_SCORE = get_or_create_histogram(
    "pack_alignment_score",
    "Pack alignment score distribution (0.0-1.0)",
    labelnames=["department_id", "pack_id"],
    buckets=[0.0, 0.25, 0.5, 0.75, 1.0],
)

PACK_SELECTOR_REQUESTS = get_or_create_counter(
    "pack_selector_requests_total",
    "Total number of pack selector requests",
    ["company_id", "status"],  # status: 'success' or 'error'
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def record_pack_activation(
    department_id: str,
    pack_id: str,
    trigger: str = "auto",
) -> None:
    """
    Record a pack activation.

    Args:
        department_id: The department UUID
        pack_id: The pack identifier
        trigger: 'auto' for automatic activation or 'manual' for user-initiated
    """
    PACK_ACTIVATIONS_TOTAL.labels(
        department_id=str(department_id),
        pack_id=str(pack_id),
        trigger=trigger,
    ).inc()


def record_alignment_score(
    department_id: str,
    pack_id: str,
    score: float,
) -> None:
    """
    Record a pack alignment score.

    Args:
        department_id: The department UUID
        pack_id: The pack identifier
        score: Alignment score between 0.0 and 1.0
    """
    PACK_ALIGNMENT_SCORE.labels(
        department_id=str(department_id),
        pack_id=str(pack_id),
    ).observe(score)


def record_selector_request(
    company_id: str,
    status: str = "success",
) -> None:
    """
    Record a pack selector request.

    Args:
        company_id: The company UUID
        status: 'success' or 'error'
    """
    PACK_SELECTOR_REQUESTS.labels(
        company_id=str(company_id),
        status=status,
    ).inc()
