"""Behavioural equivalence tests for governance router split (SP-API-002).

NOTE: The sprint brief assumed HITL/deliberation endpoints in governance,
but the actual router contains monitoring (alerts, accuracy, risk-register)
and quality (quality-check, authority-reports) endpoints. Split is pragmatic.
"""

from fastapi import APIRouter


EXPECTED_MONITORING_ROUTES = {"/api/v1/governance/alerts", "/api/v1/governance/accuracy/{agent_name}", "/api/v1/governance/risk-register"}
EXPECTED_QUALITY_ROUTES = {"/api/v1/governance/quality-check/{agent_name}", "/api/v1/governance/authority-reports"}


def _extract_paths(router):
    return {r.path for r in router.routes}


def test_governance_monitoring_routes_present():
    """Monitoring endpoints exist on the new sub-router."""
    from src.core.api.v1.governance.governance_monitoring_router import router

    paths = _extract_paths(router)
    assert EXPECTED_MONITORING_ROUTES.issubset(paths), f"Missing: {EXPECTED_MONITORING_ROUTES - paths}"


def test_governance_quality_routes_present():
    """Quality endpoints exist on the new sub-router."""
    from src.core.api.v1.governance.governance_quality_router import router

    paths = _extract_paths(router)
    assert EXPECTED_QUALITY_ROUTES.issubset(paths), f"Missing: {EXPECTED_QUALITY_ROUTES - paths}"


def test_governance_combined_router_covers_all_expected_routes():
    """Combined router covers exactly the expected route-set."""
    from src.core.api.v1.governance.router import router as combined

    paths = _extract_paths(combined)
    expected = EXPECTED_MONITORING_ROUTES | EXPECTED_QUALITY_ROUTES
    assert expected == paths, (
        f"Missing: {expected - paths}\n"
        f"Extra: {paths - expected}"
    )
