"""TDD tests -- Sprint 2 Dag 4 (PERF-002 / BP-001 / TI-003 / TI-004).

RED before fixes, GREEN after.
"""

import inspect


# ──────────────────────────────────────────────────────────────────────────────
# BP-001: audit_service.py logger.error zonder exc_info=True
# ──────────────────────────────────────────────────────────────────────────────


def test_audit_service_logger_error_has_exc_info() -> None:
    """audit_service.py logger.error() moet exc_info=True hebben (BP-001)."""
    from src.core.audit import audit_service

    src = inspect.getsource(audit_service)
    bad_patterns = [
        'logger.error(f"Failed to log security event: {e}")',
        "logger.error(f'Failed to log security event: {e}')",
    ]
    for pattern in bad_patterns:
        assert pattern not in src, (
            f"audit_service.py bevat logger.error zonder exc_info=True: {pattern!r} -- "
            "BP-001: stacktrace verloren bij security event logging failure"
        )


def test_audit_service_no_fstring_in_logger_error() -> None:
    """audit_service.py logger.error mag geen f-string gebruiken voor exception (BP-001)."""
    from src.core.audit import audit_service

    src = inspect.getsource(audit_service)
    assert 'logger.error(f"Failed to log security event: {e}")' not in src, (
        "audit_service.py gebruikt f-string in logger.error -- "
        "gebruik logger.error('...%s: %s', type(e).__name__, e, exc_info=True)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# PERF-002: LLMService.generate_response() OTel span (ADR-014)
# ──────────────────────────────────────────────────────────────────────────────


def test_llm_service_generate_response_has_otel_span() -> None:
    """LLMService.generate_response() moet een OTel span bevatten (PERF-002 / ADR-014)."""
    from src.core.llm.llm_service import LLMService

    src = inspect.getsource(LLMService.generate_response)
    has_span = (
        "get_tracer" in src
        or "tracer" in src
        or "start_as_current_span" in src
        or "@traced" in src
        or "traced(" in src
    )
    assert has_span, (
        "LLMService.generate_response() bevat geen OTel span -- "
        "PERF-002 / ADR-014: LLM latency niet zichtbaar in Jaeger/Prometheus"
    )


# ──────────────────────────────────────────────────────────────────────────────
# TI-003: experiments.py endpoints met tenant_id filter
# ──────────────────────────────────────────────────────────────────────────────


def test_experiment_model_has_tenant_id() -> None:
    """Experiment model moet tenant_id kolom hebben (TI-003)."""
    from src.core.database.models.experiment import Experiment

    assert hasattr(Experiment, "tenant_id"), (
        "Experiment model heeft geen tenant_id kolom -- "
        "TI-003: A/B test experiments zijn niet per-tenant gesoleerd"
    )


def test_experiment_list_endpoint_uses_tenant_filter() -> None:
    """list_experiments endpoint moet tenant_id filter toepassen (TI-003)."""
    from src.core.api.v1.admin import experiments

    src = inspect.getsource(experiments)
    assert "tenant_id" in src, (
        "experiments.py bevat geen tenant_id filter -- "
        "TI-003: alle 5 experiment endpoints tonen cross-tenant data"
    )


# ──────────────────────────────────────────────────────────────────────────────
# TI-004: analytics /health endpoint cross-tenant aggregaat verwijderd
# ──────────────────────────────────────────────────────────────────────────────


def test_analytics_health_no_cross_tenant_count() -> None:
    """analytics /health endpoint mag geen cross-tenant aggregaat uitvoeren (TI-004)."""
    from src.core.api import analytics_endpoints

    src = inspect.getsource(analytics_endpoints)
    # The cross-tenant count query uses sql_func.count(DBAnalyticsEvent.id) without tenant filter
    # Minimal check: health_check function should not query DBAnalyticsEvent without tenant filter
    import ast
    import textwrap

    # Find the health_check function source
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_check":
            func_src = ast.unparse(node)
            # Health check should use SELECT 1 or a simple connectivity check
            assert "DBAnalyticsEvent" not in func_src, (
                "analytics health_check() voert nog steeds query uit op DBAnalyticsEvent -- "
                "TI-004: health check toont cross-tenant event count zonder auth/tenant filter"
            )
            return
    # If health_check not found
    assert "health_check" in src, "health_check functie niet gevonden in analytics_endpoints.py"
