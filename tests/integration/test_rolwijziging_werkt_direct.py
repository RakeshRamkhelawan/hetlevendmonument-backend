"""Een rolwijziging werkt DIRECT, ook voor een sessie die al openstaat (ADR-039, scenario 6 stap 3-4).

Vraag van de regie: is het intrekken van een rol direct merkbaar, of pas bij een nieuwe token?
Gemeten tegen echte Postgres met de ECHTE `get_current_user` (alleen de databasesessie en de
CSRF-controle zijn vervangen): hetzelfde token, voor en na het toekennen of intrekken van een rol.

Uitkomst (zie de tests): de backend leest rollen en rechten bij ELK verzoek uit de database, niet uit
het token; een intrekking geldt dus op het eerstvolgende verzoek met hetzelfde token. De frontend
kent `permissions` en `isAdmin` van het moment dat `/auth/me` voor het laatst werd opgehaald (bij
inloggen en bij het herstellen van de sessie); knoppen volgen pas na verversen van de pagina. De
BACKEND weigert wel meteen.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import (  # noqa: F401
    AANVRAGER,
    COLLEGA,
    GEWONE_COLLEGA,
    TENANT,
    _sql,
    _zet_rollen,
    rollen_hersteld,
)


async def _email_van(user_id: int) -> str:
    rij = (await _sql("SELECT email FROM users WHERE id = :u", u=user_id)).one()
    return str(rij[0])


async def _vraag(app: Any, token: str, methode: str, pad: str) -> Any:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.database.database import db_manager, get_db

    async def _db() -> AsyncGenerator[Any, None]:
        async with db_manager.get_session() as session:
            yield session

    async def _geen_csrf() -> None:
        return None

    overrides = {get_db: _db, validate_csrf_token: _geen_csrf}
    app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.request(methode, pad)
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


async def _wijzig(actie: str, rol: str) -> None:
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager
    from src.core.services.rbac_service import RBACService

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            service = RBACService(session)
            ok = (
                await service.revoke_role(COLLEGA, rol, TENANT)
                if actie == "intrekken"
                else await service.assign_role(COLLEGA, rol, TENANT)
            )
    assert ok is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenRolwijzigingWerktDirectMetHetzelfdeToken:
    async def _token(self) -> str:
        from tests.integration.conftest import _build_test_token

        return _build_test_token(
            user_id=COLLEGA, email=await _email_van(COLLEGA), tenant_id=TENANT
        )

    async def test_after_revoking_the_approver_role_the_same_token_is_refused(
        self, rollen_hersteld: None, integration_app: Any
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])
        token = await self._token()
        voor = await _vraag(integration_app, token, "GET", "/api/v1/tools/hitl/pending")

        await _wijzig("intrekken", "goedkeurder")
        na = await _vraag(integration_app, token, "GET", "/api/v1/tools/hitl/pending")

        assert (voor.status_code, na.status_code) == (200, 403), (voor.text, na.text)

    async def test_after_assigning_the_approver_role_the_same_token_is_accepted(
        self, rollen_hersteld: None, integration_app: Any
    ) -> None:
        await _zet_rollen(COLLEGA, ["user"])
        token = await self._token()
        voor = await _vraag(integration_app, token, "GET", "/api/v1/tools/hitl/pending")

        await _wijzig("toekennen", "goedkeurder")
        na = await _vraag(integration_app, token, "GET", "/api/v1/tools/hitl/pending")

        assert (voor.status_code, na.status_code) == (403, 200), (voor.text, na.text)

    async def test_auth_me_follows_the_roles_with_the_same_token(
        self, rollen_hersteld: None, integration_app: Any
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])
        token = await self._token()
        voor = await _vraag(integration_app, token, "GET", "/api/v1/auth/me")

        await _wijzig("intrekken", "goedkeurder")
        na = await _vraag(integration_app, token, "GET", "/api/v1/auth/me")

        assert "receivables:approve" in voor.json()["permissions"]
        assert "receivables:approve" not in na.json()["permissions"]

    async def test_losing_the_admin_role_is_felt_with_the_same_token(
        self, rollen_hersteld: None, integration_app: Any
    ) -> None:
        # Gebruiker 101 is in de testdatabase een platform-superuser, en die blijft beheerder
        # zonder rol (`is_admin` leest ook `is_superuser`). Voor deze meting tijdelijk niet.
        oorspronkelijk = bool(
            (await _sql("SELECT is_superuser FROM users WHERE id = :u", u=COLLEGA)).one()[0]
        )
        await _sql("UPDATE users SET is_superuser = false WHERE id = :u", u=COLLEGA)
        # Er moet een ANDERE beheerder overblijven, anders weigert de backend (LAST_ADMIN): gebruiker 1
        # is daarvoor tijdelijk een gewone beheerder (geen superuser), met herstel na afloop.
        oud_actor = bool(
            (await _sql("SELECT is_superuser FROM users WHERE id = :u", u=AANVRAGER)).one()[0]
        )
        await _sql("UPDATE users SET is_superuser = false WHERE id = :u", u=AANVRAGER)
        try:
            await _zet_rollen(AANVRAGER, ["admin"])
            await _zet_rollen(COLLEGA, ["admin"])
            token = await self._token()
            voor = await _vraag(integration_app, token, "GET", "/api/v1/auth/me")

            await _wijzig("intrekken", "admin")
            na = await _vraag(integration_app, token, "GET", "/api/v1/auth/me")
        finally:
            await _sql(
                "UPDATE users SET is_superuser = :w WHERE id = :u", w=oorspronkelijk, u=COLLEGA
            )
            await _sql(
                "UPDATE users SET is_superuser = :w WHERE id = :u", w=oud_actor, u=AANVRAGER
            )

        assert (voor.json()["is_admin"], na.json()["is_admin"]) == (True, False)


async def _post(app: Any, token: str, pad: str, body: dict[str, Any]) -> Any:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.database.database import db_manager, get_db

    async def _db() -> AsyncGenerator[Any, None]:
        async with db_manager.get_session() as session:
            yield session

    async def _geen_csrf() -> None:
        return None

    overrides = {get_db: _db, validate_csrf_token: _geen_csrf}
    app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.post(pad, json=body)
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeRouteDieHetSchermGebruikt:
    """Dezelfde meting via POST /api/rbac/users/{assign,revoke}-role (wat Gebruikersbeheer aanroept)."""

    async def _token_van(self, user_id: int) -> str:
        from tests.integration.conftest import _build_test_token

        return _build_test_token(user_id=user_id, email=await _email_van(user_id), tenant_id=TENANT)

    async def test_revoking_through_the_route_is_felt_with_the_same_token(
        self, rollen_hersteld: None, integration_app: Any
    ) -> None:
        # Een gewone gebruiker als doel: COLLEGA (101) is een seed-platformbeheerder en wie geen system_admin
        # is, mag zijn rollen niet wijzigen (f9971f04, fail-secure, besluit regie 2026-10-26).
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(GEWONE_COLLEGA, ["goedkeurder"])
        beheerder = await self._token_van(AANVRAGER)
        goedkeurder = await self._token_van(GEWONE_COLLEGA)
        voor = await _vraag(integration_app, goedkeurder, "GET", "/api/v1/tools/hitl/pending")

        route = await _post(
            integration_app,
            beheerder,
            "/api/rbac/users/revoke-role",
            {"user_id": GEWONE_COLLEGA, "role_name": "goedkeurder"},
        )
        na = await _vraag(integration_app, goedkeurder, "GET", "/api/v1/tools/hitl/pending")

        assert (voor.status_code, route.status_code, na.status_code) == (200, 200, 403), (
            voor.text,
            route.text,
            na.text,
        )

    async def test_assigning_through_the_route_is_felt_with_the_same_token(
        self, rollen_hersteld: None, integration_app: Any
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["user"])
        beheerder = await self._token_van(AANVRAGER)
        gebruiker = await self._token_van(COLLEGA)
        voor = await _vraag(integration_app, gebruiker, "GET", "/api/v1/tools/hitl/pending")

        route = await _post(
            integration_app,
            beheerder,
            "/api/rbac/users/assign-role",
            {"user_id": COLLEGA, "role_name": "goedkeurder"},
        )
        na = await _vraag(integration_app, gebruiker, "GET", "/api/v1/tools/hitl/pending")

        assert (voor.status_code, route.status_code, na.status_code) == (403, 200, 200), (
            voor.text,
            route.text,
            na.text,
        )
