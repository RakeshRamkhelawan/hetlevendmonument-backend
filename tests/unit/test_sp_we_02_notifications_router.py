import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from sqlalchemy import select

from src.core.models.rbac_models import User
from src.domains.notifications.models import Notification
from tests.fixtures.auth import create_test_token


@pytest.fixture(autouse=True)
def _tenant_context_like_production():
    """Zet de tenant-ContextVar die productie altijd heeft.

    `init_tenant_auto_filtering()` (app_lifespan) registreert een globale
    `do_orm_execute`-listener die elke ORM-query filtert op de tenant uit de ContextVar, en
    die is fail-secure: geen tenant betekent NUL rijen. In productie staat die listener dus
    altijd aan en is er altijd een tenant.

    Deze tests slaagden alleen zolang de listener toevallig niet geregistreerd was in hun
    xdist-worker -- dat wil zeggen: in een configuratie die in productie nooit voorkomt.
    Draait `tests/unit/test_tenant_query_filter.py` eerder in dezelfde worker, dan vallen ze
    om. Reproduceerbaar met beide bestanden achter elkaar. Zie OP-20.

    Deze fixture maakt de tests dus realistischer, niet toleranter.
    """
    from src.core.middleware.tenant_context import set_tenant_id

    set_tenant_id(1)
    yield
    set_tenant_id(None)


class TestNotificationsRouter:
    def test_notifications_list_endpoint_registered(self):
        """Notificatie router route is geregistreerd in de app router."""
        from src.main import app
        from src.core.api.router_registry import register_all_routers

        # Registreer om zeker te zijn dat hij geladen is
        register_all_routers(app)

        routes = [str(r.path) for r in app.routes]
        assert any("/notifications" in r for r in routes)

    async def test_notifications_list_requires_auth(self, client):
        """Notificaties ophalen vereist authenticatie."""
        # Zonder headers faalt de authenticatie door de middleware
        response = client.get("/api/v1/notifications")
        assert response.status_code in (401, 403)

    async def test_notifications_list_returns_paginated(self, client, db_session):
        """Notificaties ophalen geeft een gepagineerde lijst met tenant isolatie."""
        # Genereer een valide token voor de security middlewares
        token = create_test_token(user_id=1, tenant_id=1, email="test@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Voeg dummy notificaties toe (geen hardcoded id -- laat DB auto-assign om xdist conflicts te vermijden)
        notif1 = Notification(
            tenant_id=1,
            user_id=1,  # matches mock user id 1
            type="system",
            title="Test Title 1",
            body="Test Body 1",
            channel="in_app",
            is_read=False,
        )
        notif2 = Notification(
            tenant_id=1,
            user_id=1,
            type="workflow_complete",
            title="Test Title 2",
            body="Test Body 2",
            channel="in_app",
            is_read=True,
        )
        # Notificatie van andere tenant/user (mag niet teruggegeven worden)
        notif3 = Notification(
            tenant_id=2,
            user_id=202,
            type="system",
            title="Other Tenant",
            body="Should not show",
            channel="in_app",
            is_read=False,
        )

        db_session.add_all([notif1, notif2, notif3])
        await db_session.commit()

        # Mock de user objecten voor de FastAPI route dependency (get_current_user)
        user = User(id=1, tenant_id=1, email="test@example.com", is_superuser=False)
        with (
            patch("src.core.auth.dependencies.get_current_user", return_value=user),
            patch("src.core.middleware.tenant_context.require_tenant_id", return_value=1),
        ):
            response = client.get("/api/v1/notifications?limit=10&offset=0", headers=headers)
            assert response.status_code == 200
            res_data = response.json()
            assert res_data["success"] is True
            assert len(res_data["data"]) == 2
            assert res_data["total"] == 2
            assert res_data["data"][0]["title"] in ("Test Title 1", "Test Title 2")

    @pytest.mark.timeout(120)
    async def test_notifications_mark_all_read(self, client, db_session):
        """Alle ongelezen notificaties van de user worden gemarkeerd als gelezen."""
        token = create_test_token(user_id=1, tenant_id=1, email="test@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        notif = Notification(
            tenant_id=1,
            user_id=1,  # matches mock user id 1
            type="system",
            title="Unread",
            channel="in_app",
            is_read=False,
        )
        db_session.add(notif)
        await db_session.commit()

        user = User(id=1, tenant_id=1, email="test@example.com", is_superuser=False)
        with (
            patch("src.core.auth.dependencies.get_current_user", return_value=user),
            patch("src.core.middleware.tenant_context.require_tenant_id", return_value=1),
        ):
            response = client.post("/api/v1/notifications/mark-all-read", headers=headers)
            assert response.status_code == 200
            assert response.json()["count"] >= 1

            # Verifieer in de database dat de status is aangepast
            await db_session.refresh(notif)
            assert notif.is_read is True
            assert notif.read_at is not None

    @pytest.mark.timeout(120)
    async def test_notification_mark_single_read(self, client, db_session):
        """Een enkele notificatie kan gemarkeerd worden als gelezen."""
        token = create_test_token(user_id=1, tenant_id=1, email="test@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        notif = Notification(
            tenant_id=1,
            user_id=1,  # matches mock user id 1
            type="system",
            title="Single Unread",
            channel="in_app",
            is_read=False,
        )
        db_session.add(notif)
        await db_session.flush()  # assign auto-generated id without full commit
        notif_id = notif.id
        await db_session.commit()

        user = User(id=1, tenant_id=1, email="test@example.com", is_superuser=False)
        with (
            patch("src.core.auth.dependencies.get_current_user", return_value=user),
            patch("src.core.middleware.tenant_context.require_tenant_id", return_value=1),
        ):
            response = client.post(f"/api/v1/notifications/{notif_id}/read", headers=headers)
            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["data"]["is_read"] is True

            await db_session.refresh(notif)
            assert notif.is_read is True

    async def test_notification_tenant_isolation(self, client, db_session):
        """Gebruiker van tenant A kan notificaties van tenant B niet als gelezen markeren of inzien."""
        token = create_test_token(user_id=1, tenant_id=1, email="test@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Notificatie op tenant 2 (geen hardcoded id -- laat DB auto-assign)
        notif = Notification(
            tenant_id=2,
            user_id=202,
            type="system",
            title="Tenant 2 Notif",
            channel="in_app",
            is_read=False,
        )
        db_session.add(notif)
        await db_session.flush()
        notif_id = notif.id
        await db_session.commit()

        user = User(id=1, tenant_id=1, email="test@example.com", is_superuser=False)
        # Gebruiker probeert markeren met tenant 1 context
        with (
            patch("src.core.auth.dependencies.get_current_user", return_value=user),
            patch("src.core.middleware.tenant_context.require_tenant_id", return_value=1),
        ):
            response = client.post(f"/api/v1/notifications/{notif_id}/read", headers=headers)
            assert response.status_code == 404


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over rollen en de middlewareketen, niet over de accountstatus, en hebben geen database.

    De controle zelf (uitgezet = 401 ACCOUNT_DISABLED, database weg = 503) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, tegen een echte database.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import account_status

    with patch.object(
        account_status,
        "haal_account_status",
        AsyncMock(return_value=account_status.AccountStatus.ACTIEF),
    ):
        yield
