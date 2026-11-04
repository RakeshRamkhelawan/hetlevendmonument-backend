"""Een niet-beheerder krijgt 403 voordat zijn body gevalideerd wordt (plan nazorg, punt d).

Tot 2026-10-08 stond de rolcontrole van deze beheerroutes in de handler. FastAPI valideert de
body daarvoor, dus een niet-beheerder met een lege body kreeg 422 met de veldnamen en regels van
het schema. Nu staat de controle in de dependencies.

Wat bewust NIET verandert: kapotte JSON geeft 422, ook voor een niet-beheerder. FastAPI leest
de body voordat het de dependencies oplost. Dat lekt alleen "dit is geen JSON" en geen schema;
het dichten zou autorisatie in middleware vragen, met dubbele routekennis. Geaccepteerd, en
hieronder vastgelegd zodat het een keuze blijft en geen ongeluk.

Een kale app met alleen de geraakte routers; gebruiker en database zijn dubbels.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.exceptions import register_exception_handlers
from src.core.auth.auth_service import UserResponse

TENANT = 7

#: (methode, pad) van beheerroutes met een body. `{}` is overal een ongeldige body.
BEHEERROUTES: list[tuple[str, str]] = [
    ("POST", "/api/rbac/roles/create"),
    ("POST", "/api/rbac/roles/3/permissions"),
    ("DELETE", "/api/rbac/roles/3/permissions"),
    ("POST", "/api/rbac/users/assign-role"),
    ("POST", "/api/rbac/users/revoke-role"),
    ("POST", "/api/rbac/users/assign-role/bulk"),
    ("POST", "/api/rbac/users/revoke-role/bulk"),
    ("POST", "/api/admin/features/x/toggle?target_tenant_id=7"),
    ("POST", "/api/gdpr/delete-all"),
    ("PUT", "/api/v1/tools/hitl/four-eyes"),
    ("POST", "/api/v1/gatekeeper/hitl/approve"),
    ("POST", "/api/v1/gatekeeper/hitl/reject"),
    ("POST", "/api/v1/domain-packs"),
    ("PUT", "/api/v1/domain-packs/00000000-0000-0000-0000-000000000001"),
    ("POST", "/execute"),
    ("POST", "/api/v1/tenants/"),
    ("PUT", "/api/v1/tenants/99"),
    ("POST", "/api/v1/users/?target_tenant_id=99"),
]


def _gebruiker(*, beheerder: bool) -> UserResponse:
    return UserResponse(
        id=5,
        email="u5@klant.nl",
        tenant_id=TENANT,
        roles=["admin", "tenant_admin"] if beheerder else ["user"],
        is_superuser=beheerder,
    )


def _app(monkeypatch: pytest.MonkeyPatch, *, beheerder: bool) -> TestClient:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api import domain_packs
    from src.core.api.v1.feature_flags import admin_router as ff_admin
    from src.core.api.v1.gatekeeper import gatekeeper_hitl_router
    from src.core.api.v1.gdpr_compliance import erasure_router
    from src.core.api.v1.rbac import assignment_router, dependencies as rbac_deps, roles_router
    from src.core.api.v1.tenants.tenants_detail_router import tenants_detail_router
    from src.core.api.v1.tenants.tenants_list_router import tenants_list_router
    from src.core.api.v1.terminal import router as terminal
    from src.core.api.v1.tool_broker import four_eyes_router
    from src.core.api.v1.users.users_list_router import users_list_router
    from src.core.auth import dependencies as auth_deps
    from src.core.database.database import get_db

    monkeypatch.setattr(rbac_deps, "require_tenant_id", lambda: TENANT)
    monkeypatch.setattr(
        rbac_deps.RBACService, "user_has_permission", AsyncMock(return_value=beheerder)
    )
    monkeypatch.setenv("ENVIRONMENT", "test")

    app = FastAPI()

    register_exception_handlers(app)
    app.include_router(roles_router.router, prefix="/api")
    app.include_router(assignment_router.router, prefix="/api")
    app.include_router(ff_admin.router, prefix="/api")
    app.include_router(erasure_router.router)
    app.include_router(four_eyes_router.router)
    app.include_router(gatekeeper_hitl_router.router)
    app.include_router(domain_packs.router)
    app.include_router(terminal.router)
    app.include_router(tenants_list_router, prefix="/api/v1/tenants")
    app.include_router(tenants_detail_router, prefix="/api/v1/tenants")
    app.include_router(users_list_router, prefix="/api/v1/users")

    gebruiker = _gebruiker(beheerder=beheerder)
    app.dependency_overrides[auth_deps.get_current_user] = lambda: gebruiker
    app.dependency_overrides[auth_deps.get_current_user_dependency] = lambda: gebruiker
    app.dependency_overrides[auth_deps.get_current_user_id] = lambda: gebruiker.id
    app.dependency_overrides[rbac_deps.get_current_user_id] = lambda: gebruiker.id
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def niet_beheerder(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield _app(monkeypatch, beheerder=False)


@pytest.mark.unit
@pytest.mark.parametrize(("methode", "pad"), BEHEERROUTES)
def test_a_non_admin_with_an_invalid_body_gets_403_not_422(
    niet_beheerder: TestClient, methode: str, pad: str
) -> None:
    response = niet_beheerder.request(methode, pad, json={})
    assert response.status_code == 403, (response.status_code, response.text)
    # Geen schema-informatie in de weigering.
    assert "Field required" not in response.text


@pytest.mark.unit
@pytest.mark.parametrize(("methode", "pad"), BEHEERROUTES[:3])
def test_broken_json_from_a_non_admin_gives_422_and_that_is_accepted(
    niet_beheerder: TestClient, methode: str, pad: str
) -> None:
    """Gedocumenteerde keuze (zie de moduledocstring): geen geldige JSON -> 422."""
    response = niet_beheerder.request(
        methode, pad, content=b"{kapot", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "json_invalid"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("methode", "pad"),
    [
        ("POST", "/api/rbac/roles/create"),
        ("POST", "/api/rbac/users/assign-role"),
        ("POST", "/api/v1/domain-packs"),
        ("POST", "/api/v1/tenants/"),
        ("POST", "/api/gdpr/delete-all"),
    ],
)
def test_an_admin_with_an_invalid_body_still_gets_422(
    monkeypatch: pytest.MonkeyPatch, methode: str, pad: str
) -> None:
    """De andere helft: zonder dit is 'altijd 403' een geldige oplossing voor de test hierboven."""
    response = _app(monkeypatch, beheerder=True).request(methode, pad, json={})
    assert response.status_code == 422, (response.status_code, response.text)


def _tenant_app(gebruiker: UserResponse) -> TestClient:
    """Alleen de tenantdetailrouter; de servicelaag is een dubbel dat niets vindt (404)."""
    from src.core.api.v1.tenants import dependencies as tenant_deps
    from src.core.api.v1.tenants.tenants_detail_router import tenants_detail_router
    from src.core.auth import dependencies as auth_deps

    service = AsyncMock()
    service.update_tenant = AsyncMock(return_value=None)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(tenants_detail_router, prefix="/api/v1/tenants")
    app.dependency_overrides[auth_deps.get_current_user] = lambda: gebruiker
    app.dependency_overrides[tenant_deps.get_tenant_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.unit
def test_a_plain_user_cannot_update_his_own_tenant() -> None:
    """Gat uit nazorg 2: de PUT toetste alleen de tenantgrens, niet de rol."""
    gebruiker = UserResponse(id=5, email="u5@klant.nl", tenant_id=TENANT, roles=["user"])
    response = _tenant_app(gebruiker).put(f"/api/v1/tenants/{TENANT}", json={"name": "x"})
    assert response.status_code == 403, (response.status_code, response.text)
    assert response.json()["detail"] == "Admin role required"


@pytest.mark.unit
def test_a_tenant_admin_passes_the_role_check_on_his_own_tenant() -> None:
    """De andere helft: een beheerder (geen superuser) komt door de controle tot de service."""
    gebruiker = UserResponse(id=6, email="a6@klant.nl", tenant_id=TENANT, roles=["admin"])
    response = _tenant_app(gebruiker).put(f"/api/v1/tenants/{TENANT}", json={"name": "x"})
    assert response.status_code == 404, (response.status_code, response.text)
