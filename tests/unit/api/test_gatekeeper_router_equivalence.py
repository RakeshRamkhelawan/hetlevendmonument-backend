"""Behavioural equivalence tests for gatekeeper router split (SP-API-002).

NOTE: The sprint brief assumed policy-CRUD/allowlist/blocklist endpoints,
but the actual router contains decisions (list, get, chain) and HITL
(approve, reject) plus stats endpoints. Split is pragmatic.
"""

from fastapi import APIRouter
from fastapi.routing import APIRoute, APIWebSocketRoute


EXPECTED_DECISIONS_ROUTES = {
    "/api/v1/gatekeeper/decisions",
    "/api/v1/gatekeeper/decisions/{task_id}",
    "/api/v1/gatekeeper/decisions/{task_id}/chain",
    "/api/v1/gatekeeper/stats",
}
EXPECTED_HITL_ROUTES = {"/api/v1/gatekeeper/hitl/approve", "/api/v1/gatekeeper/hitl/reject"}


def _extract_paths(router):
    paths: set[str] = set()
    for route in router.routes:
        if isinstance(route, (APIRoute, APIWebSocketRoute)):
            paths.add(route.path)
        elif hasattr(route, "routes"):
            paths.update(_extract_paths(route))
    return paths


def test_gatekeeper_decisions_routes_present():
    """Decisions endpoints exist on the new sub-router."""
    from src.core.api.v1.gatekeeper.gatekeeper_decisions_router import router

    paths = _extract_paths(router)
    assert EXPECTED_DECISIONS_ROUTES.issubset(paths), f"Missing: {EXPECTED_DECISIONS_ROUTES - paths}"


def test_gatekeeper_hitl_routes_present():
    """HITL endpoints exist on the new sub-router."""
    from src.core.api.v1.gatekeeper.gatekeeper_hitl_router import router

    paths = _extract_paths(router)
    assert EXPECTED_HITL_ROUTES.issubset(paths), f"Missing: {EXPECTED_HITL_ROUTES - paths}"


def test_gatekeeper_combined_router_covers_all_expected_routes():
    """Combined router covers exactly the expected route-set."""
    from src.core.api.v1.gatekeeper.router import router as combined

    paths = _extract_paths(combined)
    expected = EXPECTED_DECISIONS_ROUTES | EXPECTED_HITL_ROUTES
    assert expected == paths, (
        f"Missing: {expected - paths}\n"
        f"Extra: {paths - expected}"
    )
