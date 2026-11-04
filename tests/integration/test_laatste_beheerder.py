"""Een tenant houdt altijd minstens een actieve beheerder (ADR-039, besluit regie 2026-10-10).

Gemeten tegen echte Postgres:
1. Een intrekking van de beheerdersrol die de tenant zonder actieve beheerder zou laten, wordt
   geweigerd met 409 en code LAST_ADMIN -- en er verandert niets.
2. Twee beheerders die elkaar TEGELIJK intrekken: precies een slaagt (rijvergrendeling).
3. Hetzelfde voor bulk-intrekken, voor het deactiveren of verwijderen van de laatste beheerder
   (`PUT`/`DELETE /api/v1/users/{id}`) en voor het vervangen van zijn rollen (`PUT ... role_ids`).
4. De platform-superuser telt NIET als beheerder van de tenant (F7).
5. Een rol intrekken die de gebruiker niet heeft: False/404 en GEEN auditregel.

Isolatie: de testdatabase heeft meer beheerders in tenant 1. Elke test zet de toestand eerst zo dat
precies de gewenste gebruikers beheerder zijn, en herstelt daarna rollen en `is_superuser`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import (  # noqa: F401
    AANVRAGER,
    COLLEGA,
    TENANT,
    _sql,
    _zet_rollen,
    rollen_hersteld,
)

ADMIN_NAMEN = ("admin", "system_admin", "tenantadmin")


@pytest_asyncio.fixture
async def beheerders_geisoleerd(rollen_hersteld: None) -> AsyncGenerator[None, None]:
    """Maak gebruikers 1 en 101 de enige actieve beheerders van tenant 1; herstel daarna alles."""
    oud_links = list(
        (
            await _sql(
                "SELECT ur.user_id, ur.role_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                "WHERE r.tenant_id = :t AND lower(r.name) IN ('admin','system_admin','tenantadmin')",
                t=TENANT,
            )
        ).all()
    )
    oud_flags = {
        int(r[0]): (bool(r[1]), bool(r[2]))
        for r in (
            await _sql(
                "SELECT id, is_superuser, is_active FROM users WHERE id IN (:a, :c)",
                a=AANVRAGER,
                c=COLLEGA,
            )
        ).all()
    }
    await _sql(
        "DELETE FROM user_roles WHERE tenant_id = :t AND role_id IN "
        "(SELECT id FROM roles WHERE tenant_id = :t AND lower(name) IN "
        "('admin','system_admin','tenantadmin'))",
        t=TENANT,
    )
    await _sql(
        "UPDATE users SET is_superuser = false, is_active = true WHERE id IN (:a, :c)",
        a=AANVRAGER,
        c=COLLEGA,
    )
    yield
    await _sql(
        "DELETE FROM user_roles WHERE tenant_id = :t AND role_id IN "
        "(SELECT id FROM roles WHERE tenant_id = :t AND lower(name) IN "
        "('admin','system_admin','tenantadmin'))",
        t=TENANT,
    )
    for user_id, role_id in oud_links:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t) "
            "ON CONFLICT DO NOTHING",
            u=user_id,
            r=role_id,
            t=TENANT,
        )
    for user_id, (superuser, actief) in oud_flags.items():
        await _sql(
            "UPDATE users SET is_superuser = :s, is_active = :a WHERE id = :u",
            s=superuser,
            a=actief,
            u=user_id,
        )


async def _admins() -> set[int]:
    rijen = (
        await _sql(
            "SELECT DISTINCT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "JOIN users u ON u.id = ur.user_id WHERE r.tenant_id = :t AND u.tenant_id = :t "
            "AND lower(r.name) IN ('admin','system_admin','tenantadmin') AND u.is_active "
            "AND u.deleted_at IS NULL AND NOT u.is_superuser",
            t=TENANT,
        )
    ).all()
    return {int(r[0]) for r in rijen}


async def _token_van(user_id: int) -> str:
    from tests.integration.conftest import _build_test_token

    email = str((await _sql("SELECT email FROM users WHERE id = :u", u=user_id)).one()[0])
    return _build_test_token(user_id=user_id, email=email, tenant_id=TENANT)


async def _aanroep(
    app: Any, token: str, methode: str, pad: str, body: dict[str, Any] | None = None
) -> Any:
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
            return await client.request(methode, pad, json=body)
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


async def _revoke_service(user_id: int, rol: str) -> Any:
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager
    from src.core.services.rbac_service import RBACService

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            return await RBACService(session).revoke_role(user_id, rol, TENANT)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeLaatsteBeheerderBlijft:
    async def test_revoking_the_last_admin_role_through_the_route_is_409_last_admin(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        # Actor 1 is een platform-superuser met beheerrechten maar telt niet mee; 101 is de laatste.
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "POST",
            "/api/rbac/users/revoke-role",
            {"user_id": COLLEGA, "role_name": "admin"},
        )

        assert antwoord.status_code == 409, antwoord.text
        assert "LAST_ADMIN" in antwoord.text

    async def test_the_last_admin_keeps_the_role_after_the_refusal(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "POST",
            "/api/rbac/users/revoke-role",
            {"user_id": COLLEGA, "role_name": "admin"},
        )

        assert await _admins() == {COLLEGA}

    async def test_revoking_an_admin_role_is_allowed_when_another_admin_remains(
        self, beheerders_geisoleerd: None
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        gelukt = await _revoke_service(COLLEGA, "admin")

        assert gelukt is True
        assert await _admins() == {AANVRAGER}

    async def test_a_platform_superuser_does_not_count_as_a_tenant_admin(
        self, beheerders_geisoleerd: None
    ) -> None:
        from src.core.exceptions import ConflictError

        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        with pytest.raises(ConflictError):
            await _revoke_service(COLLEGA, "admin")

    async def test_two_admins_revoking_each_other_at_the_same_time_leave_exactly_one(
        self, beheerders_geisoleerd: None
    ) -> None:
        from src.core.exceptions import ConflictError

        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        uitslag = await asyncio.gather(
            _revoke_service(AANVRAGER, "admin"),
            _revoke_service(COLLEGA, "admin"),
            return_exceptions=True,
        )

        gelukt = [u for u in uitslag if u is True]
        geweigerd = [u for u in uitslag if isinstance(u, ConflictError)]
        assert (len(gelukt), len(geweigerd), len(await _admins())) == (1, 1, 1), uitslag

    async def test_bulk_revoke_reports_last_admin_per_user_instead_of_failing_everything(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "POST",
            "/api/rbac/users/revoke-role/bulk",
            {"user_ids": [COLLEGA], "role_name": "admin"},
        )

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["results"][0]["success"] is False
        assert antwoord.json()["results"][0]["error"] == "LAST_ADMIN"
        assert await _admins() == {COLLEGA}

    async def test_deleting_the_last_admin_through_the_users_route_is_409(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _aanroep(
            integration_app, await _token_van(AANVRAGER), "DELETE", f"/api/v1/users/{COLLEGA}"
        )

        assert antwoord.status_code == 409, antwoord.text
        assert await _admins() == {COLLEGA}

    async def test_deactivating_the_last_admin_through_the_users_route_is_409(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "PUT",
            f"/api/v1/users/{COLLEGA}",
            {"is_active": False},
        )

        assert antwoord.status_code == 409, antwoord.text
        assert await _admins() == {COLLEGA}

    async def test_replacing_the_roles_of_the_last_admin_through_the_users_route_is_409(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=AANVRAGER)
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin"])
        rol_user = int(
            (
                await _sql("SELECT id FROM roles WHERE tenant_id = :t AND name = 'user'", t=TENANT)
            ).one()[0]
        )

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "PUT",
            f"/api/v1/users/{COLLEGA}",
            {"role_ids": [rol_user]},
        )

        assert antwoord.status_code == 409, antwoord.text
        assert await _admins() == {COLLEGA}


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenRolIntrekkenDieDeGebruikerNietHeeft:
    async def test_the_service_returns_false(self, beheerders_geisoleerd: None) -> None:
        await _zet_rollen(COLLEGA, ["user"])

        assert await _revoke_service(COLLEGA, "goedkeurder") is False

    async def test_no_audit_event_is_written(self, beheerders_geisoleerd: None) -> None:
        from src.core.database.bypass_session import adopt_tenant
        from src.core.database.database import db_manager
        from src.core.services.rbac_service import RBACService

        await _zet_rollen(COLLEGA, ["user"])
        emit = AsyncMock()
        async with db_manager.get_session() as session:
            async with adopt_tenant(session, TENANT):
                with patch("src.core.services.rbac_service.governance_bus.emit", emit):
                    await RBACService(session).revoke_role(COLLEGA, "goedkeurder", TENANT)

        emit.assert_not_awaited()

    async def test_the_route_answers_404(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["user"])

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "POST",
            "/api/rbac/users/revoke-role",
            {"user_id": COLLEGA, "role_name": "goedkeurder"},
        )

        assert antwoord.status_code == 404, antwoord.text
