"""De twee `POST /api/v1/approvals/{id}/respond`-routes en `approval_requests` bestaan niet meer
(ADR-036 OP-264, herziening 2026-10-04, punt 2).

Waarom: die route bewaarde een beslissing in een Python-lijst van het proces (geen database,
geen auditregel) en antwoordde 404 op alles wat een echte dock-stap kon sturen. De enige weg voor
een menselijke goedkeuring is `/api/v1/tools/hitl/approve|reject` (`hitl_tickets`).

Getoetst tegen de ECHT gebouwde app (`create_test_app()` registreert alle routers; `create_app`
met `testing=True` doet dat niet, zie `test_frontend_backend_endpoint_contract.py`) en tegen de
modules zelf -- niet tegen een zelfverzonnen FastAPI-app. De controlegroep bewijst dat de
routelijst echt is: de tool-broker-routes staan er WEL in.

Geen autouse-fixture in `tests/conftest.py` of `tests/architecture/conftest.py` raakt de
routelijst of `app_state`: `enforce_testing_env` zet alleen TESTING, `_reset_global_state` herstelt
singletons en de tenantfilter-listener. Gecontroleerd 2026-10-04.

Niet getoetst, bewust: `GET /api/v1/approvals`. De brief noemt alleen de twee respond-routes; of
die leesroute verdwijnt of een lege lijst geeft, beslist de bouwer.

Mutatiebewijs (daadwerkelijk gedraaid, zie de terugmelding van taak 1): het respond-pad in een van
de twee routerbestanden terugzetten maakt `test_no_post_approvals_respond_route_in_the_built_app`
rood; `approval_requests` terugzetten in `management_endpoints` of `app_state` maakt de
bijbehorende attribuut-/sleuteltest rood; een route onder een andere pad-naam (`/approve`) blijft
groen.
"""

from __future__ import annotations

import re
from typing import Any, cast

import pytest

_RESPOND = re.compile(r"/approvals/\{[^}]+\}/respond$")


@pytest.fixture(scope="module")
def built_app_routes() -> list[tuple[str, frozenset[str]]]:
    from src.main import create_test_app

    app = create_test_app()
    return [
        (cast(Any, r).path, frozenset(getattr(r, "methods", None) or ()))
        for r in app.routes
        if hasattr(r, "path")
    ]


def test_the_route_list_is_the_real_one(built_app_routes: list[tuple[str, frozenset[str]]]) -> None:
    """Controlegroep: de lijst bevat de weg die WEL blijft."""
    assert ("/api/v1/tools/hitl/approve", frozenset({"POST"})) in built_app_routes


def test_no_post_approvals_respond_route_in_the_built_app(
    built_app_routes: list[tuple[str, frozenset[str]]],
) -> None:
    gevonden = [p for p, methods in built_app_routes if "POST" in methods and _RESPOND.search(p)]

    assert gevonden == [], f"nog een goedkeurroute op procesgeheugen in de echte app: {gevonden}"


def test_management_endpoints_has_no_approval_requests_list() -> None:
    import src.core.api.management_endpoints as module

    assert not hasattr(module, "approval_requests")


def test_management_endpoints_has_no_process_approval_handler() -> None:
    import src.core.api.management_endpoints as module

    assert not hasattr(module, "process_approval")


def test_tasks_router_has_no_process_approval_handler() -> None:
    import src.core.api.v1.management.tasks_router as module

    assert not hasattr(module, "process_approval")


def test_tasks_router_does_not_import_approval_requests() -> None:
    import src.core.api.v1.management.tasks_router as module

    assert not hasattr(module, "approval_requests")


def test_app_state_has_no_approval_requests_key() -> None:
    from src.core.shared.app_state import app_state

    assert "approval_requests" not in app_state
