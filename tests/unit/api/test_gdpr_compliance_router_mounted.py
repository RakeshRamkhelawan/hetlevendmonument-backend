"""AUDIT-ARCH-2026-07-02 Dag 2 losse P1 -- SAA-001 / gdpr-explanation-router-unmounted.

`explanation_router.py` (EU AI Act Art. 13/86 -- AI Decision Explainability,
`GET /api/gdpr/decisions/{decision_id}/explanation`) bestaat maar werd niet
opgenomen in de composiet-router (`src/core/api/v1/gdpr_compliance/router.py`),
die alleen portability/erasure/access/utility_router assembleert. Het
compliance-relevante explainability-endpoint was daardoor nooit bereikbaar.
"""

from src.core.api.v1.gdpr_compliance.router import router


def test_explanation_route_is_registered_on_composite_router() -> None:
    """De explainability-route moet aanwezig zijn op de samengestelde GDPR-router."""
    route_paths = [getattr(route, "path", "") for route in router.routes]
    assert "/api/gdpr/decisions/{decision_id}/explanation" in route_paths, (
        "GET /api/gdpr/decisions/{decision_id}/explanation ontbreekt op de "
        "samengestelde gdpr_compliance-router -- explanation_router.py is nooit "
        "opgenomen via router.include_router() (SAA-001)."
    )
