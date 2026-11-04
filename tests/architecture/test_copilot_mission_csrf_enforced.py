"""Architecture guard: state-changing copilot + mission endpoints MUST enforce CSRF.

SEC-010 CSRF is a Redis-backed fetched-token scheme (validate_csrf_token in
src/core/api/auth/dependencies.py). The frontend already sends X-CSRF-Token on
these calls; the backend must actually validate it. This test introspects the
real FastAPI route dependency trees (not source text), so it turns RED the moment
a governed state-changing route is added or refactored without CSRF enforcement.

Context: AGENTIC-COPILOT-TAAKBEHEER dag-5 hardening -- close the CSRF theater gap.
"""

from fastapi.routing import APIRoute

from src.core.api.auth.dependencies import validate_csrf_token

# IMPORTANT: import the ASSEMBLED/registered router for each surface, never a leaf
# sub-router. The mission surface is composed of crud_router + lifecycle_router via
# missions.router; importing only crud_router once hid lifecycle_router's
# approve/reject mutations from this guard. turn_endpoint and copilot audit_endpoints
# are registered directly as leaves, so their own router IS the assembled surface.
from src.core.api.v1.missions.router import router as missions_router
from src.core.copilot.api.audit_endpoints import router as audit_router
from src.core.copilot.api.turn_endpoint import router as turn_router


def _flatten(dependant):
    out = [dependant]
    for sub in dependant.dependencies:
        out.extend(_flatten(sub))
    return out


def _route_enforces_csrf(route: APIRoute) -> bool:
    return validate_csrf_token in [d.call for d in _flatten(route.dependant)]


# HTTP methods that mutate server state and therefore require CSRF protection.
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Every governed router whose state-changing endpoints MUST enforce CSRF (SEC-010).
_GOVERNED_ROUTERS = [
    ("turn", turn_router),
    ("missions", missions_router),
    ("audit", audit_router),
]

# Explicit, reviewed exemptions: (router_name, METHOD, path) tuples that
# intentionally do NOT enforce CSRF. Keep this EMPTY unless there is a documented
# reason -- every entry is a hole in the CSRF defense and needs justification.
_CSRF_EXEMPT: set[tuple[str, str, str]] = set()


def test_all_mutating_copilot_mission_routes_enforce_csrf():
    """Fail closed: enumerate EVERY mutating route on the governed routers and
    require CSRF. A newly added state-changing endpoint is caught automatically --
    it does not need to be added to any allowlist -- so the gap that let
    respond_to_proactive_signal slip through cannot recur.
    """
    unhardened: list[str] = []
    for name, router in _GOVERNED_ROUTERS:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in sorted(route.methods & _MUTATING_METHODS):
                if (name, method, route.path) in _CSRF_EXEMPT:
                    continue
                if not _route_enforces_csrf(route):
                    unhardened.append(f"{name} {method} {route.path}")

    assert not unhardened, (
        "These mutating copilot/mission endpoints do not enforce CSRF "
        "(add Depends(validate_csrf_token), or add a justified entry to "
        "_CSRF_EXEMPT): " + "; ".join(sorted(unhardened))
    )
