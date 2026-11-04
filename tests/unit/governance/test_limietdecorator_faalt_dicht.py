"""Een limietdecorator zonder `Request` faalt bij het DECOREREN, en de limiet werkt echt.

Brief 2026-10-25 (rate limit faalt dicht). Wat er stond: de decorators zochten de `Request` tussen
de argumenten en voerden de route zonder limiet uit als ze er geen vonden. Gemeten: 38 van 109
routes hadden geen `Request` en dus geen limiet (o.a. het wissen en exporteren van leergegevens en
alle ActivePieces-routes).

Wat deze tests bewaken:

- elke decorator uit beide modules weigert een functie zonder `Request` bij het importeren;
- een functie MET `Request` (ook als string-annotatie) wordt gewoon geaccepteerd -- zonder deze
  helft is "weiger alles" een geldige oplossing;
- op een van de 38 routes volgt na het maximum aantal aanroepen een 429 (nu: nooit).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient

from src.core.activepieces.service import get_activepieces_service
from src.core.api.v1.activepieces import connections_router
from src.core.auth.api_deps import get_current_user
from src.core.governance import rate_limiter as governance_limiter
from src.core.shared import rate_limiter as shared_limiter

pytestmark = pytest.mark.unit

# Alle decorators uit beide modules, zoals ze op een route staan.
DECORATORS: dict[str, Callable[[Callable[..., Any]], Callable[..., Any]]] = {
    "privacy_rate_limit": shared_limiter.privacy_rate_limit(max_requests=5, window_seconds=60),
    "consent_update_limit": shared_limiter.consent_update_limit,
    "ai_transparency_limit": shared_limiter.ai_transparency_limit,
    "copilot_turn_limit": governance_limiter.copilot_turn_limit(),
    "cva_chat_limit": governance_limiter.cva_chat_limit,
    "agent_execute_limit": governance_limiter.agent_execute_limit,
    "integration_read_limit": governance_limiter.integration_read_limit,
    "integration_write_limit": governance_limiter.integration_write_limit,
    "governance_read_limit": governance_limiter.governance_read_limit,
    "governance_write_limit": governance_limiter.governance_write_limit,
    "dsar_export_limit": governance_limiter.dsar_export_limit,
    "dsar_delete_limit": governance_limiter.dsar_delete_limit,
    "consent_read_limit": governance_limiter.consent_read_limit,
    "human_review_limit": governance_limiter.human_review_limit,
    "hr_import_read_limit": governance_limiter.hr_import_read_limit,
    "hr_import_write_limit": governance_limiter.hr_import_write_limit,
    "pack_activation_read_limit": governance_limiter.pack_activation_read_limit,
    "pack_activation_write_limit": governance_limiter.pack_activation_write_limit,
    "snapshot_read_limit": governance_limiter.snapshot_read_limit,
    "snapshot_write_limit": governance_limiter.snapshot_write_limit,
    "portal_public_read_limit": governance_limiter.portal_public_read_limit,
    "portal_public_write_limit": governance_limiter.portal_public_write_limit,
    "portal_auth_limit": governance_limiter.portal_auth_limit,
    "portal_magic_link_email_limit": governance_limiter.portal_magic_link_email_limit,
    "portal_takedown_limit": governance_limiter.portal_takedown_limit,
    "portal_newsletter_limit": governance_limiter.portal_newsletter_limit,
}


async def _zonder_request(naam: str) -> dict[str, str]:
    return {"naam": naam}


async def _met_request(request: Request) -> dict[str, str]:
    return {"pad": request.url.path}


@pytest.mark.parametrize("naam", sorted(DECORATORS))
def test_een_functie_zonder_request_wordt_bij_het_decoreren_geweigerd(naam: str) -> None:
    with pytest.raises(TypeError, match="Request"):
        DECORATORS[naam](_zonder_request)


@pytest.mark.parametrize("naam", sorted(DECORATORS))
def test_een_functie_met_request_wordt_geaccepteerd(naam: str) -> None:
    assert callable(DECORATORS[naam](_met_request))


def test_de_foutmelding_noemt_de_functie_zodat_je_de_route_vindt() -> None:
    with pytest.raises(TypeError, match="_zonder_request"):
        shared_limiter.privacy_rate_limit(max_requests=1, window_seconds=60)(_zonder_request)


def test_een_parameter_die_toevallig_request_heet_maar_geen_request_is_telt_niet() -> None:
    async def _body(request: dict[str, str]) -> None:
        return None

    with pytest.raises(TypeError):
        shared_limiter.privacy_rate_limit(max_requests=1, window_seconds=60)(_body)


def test_een_string_annotatie_request_telt_wel() -> None:
    # `from __future__ import annotations` maakt van elke annotatie een string.
    assert _met_request.__annotations__["request"] == "Request"
    shared_limiter.privacy_rate_limit(max_requests=1, window_seconds=60)(_met_request)


@pytest.fixture
def schone_limiter() -> Iterator[None]:
    shared_limiter._rate_limiter._requests.clear()
    yield
    shared_limiter._rate_limiter._requests.clear()


def _app_met_activepieces_route() -> TestClient:
    dienst = MagicMock()
    dienst.list_connections = AsyncMock(return_value=[])
    app = FastAPI()
    app.include_router(connections_router.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, tenant_id=1)
    app.dependency_overrides[get_activepieces_service] = lambda: dienst
    return TestClient(app)


def test_op_een_route_die_geen_limiet_had_volgt_na_het_maximum_een_429(
    schone_limiter: None,
) -> None:
    """`GET /integrations/connections` heeft `integration_read_limit` (60 per minuut)."""
    client = _app_met_activepieces_route()

    statussen = [client.get("/integrations/connections").status_code for _ in range(61)]

    assert statussen[-1] == 429


def test_op_diezelfde_route_zijn_de_eerste_zestig_aanroepen_toegestaan(
    schone_limiter: None,
) -> None:
    client = _app_met_activepieces_route()

    statussen = [client.get("/integrations/connections").status_code for _ in range(60)]

    assert set(statussen) == {200}


def _app_met_volgorde(limiet_boven_route: bool) -> TestClient:
    router = APIRouter()

    async def _eind(request: Request) -> dict[str, str]:
        return {"ok": request.url.path}

    limiet = shared_limiter.privacy_rate_limit(max_requests=2, window_seconds=60)
    if limiet_boven_route:
        route = limiet(router.get("/x")(_eind))
    else:
        route = router.get("/x")(limiet(_eind))
    assert callable(route)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_een_limiet_boven_de_routedecorator_doet_niets(schone_limiter: None) -> None:
    """Het mechanisme achter de zes routes die de architectuurtest nu weigert."""
    client = _app_met_volgorde(limiet_boven_route=True)

    statussen = [client.get("/x").status_code for _ in range(4)]

    assert statussen == [200, 200, 200, 200]


def test_een_limiet_onder_de_routedecorator_geeft_na_het_maximum_een_429(
    schone_limiter: None,
) -> None:
    client = _app_met_volgorde(limiet_boven_route=False)

    statussen = [client.get("/x").status_code for _ in range(3)]

    assert statussen == [200, 200, 429]
