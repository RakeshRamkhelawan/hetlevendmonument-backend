"""De vier-ogen-instelling per actie lezen en wijzigen (ADR-039, debiteurenagent dag 3).

`GET /api/v1/tools/hitl/four-eyes`: iedere gebruiker van de tenant ziet per actie of vier ogen
aan staat. `PUT`: alleen een tenantbeheerder, alleen namen uit de catalogus, altijd de EIGEN
tenant (uit de JWT), met een auditregel.

Echte SQLite-sessie: de instelling wordt echt in `tenants.settings` geschreven en teruggelezen.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.auth.auth_service import UserResponse

PAD = "/api/v1/tools/hitl/four-eyes"


def _gebruiker(tenant_id: int, roles: list[str]) -> UserResponse:
    return UserResponse(id=5, email="b@klant.nl", tenant_id=tenant_id, roles=roles)


async def _tenants(db: AsyncSession) -> None:
    from src.core.models.rbac_models import Tenant

    db.add(Tenant(id=1, name="Een", slug="een", settings={}))
    db.add(Tenant(id=2, name="Twee", slug="twee", settings={"four_eyes_actions": ["make_payment"]}))
    await db.commit()


def _client(
    db: AsyncSession, gebruiker: UserResponse, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, AsyncMock]:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.tool_broker import four_eyes_router as module
    from src.core.api.v1.tool_broker.dependencies import get_db
    from src.core.api.v1.admin.dependencies import get_current_user

    audit = AsyncMock(return_value=None)
    monkeypatch.setattr(module.AuditService, "log_event", audit)
    app = FastAPI()
    app.include_router(module.router)

    async def _db() -> Any:
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app), audit


def _aan(antwoord: dict[str, Any]) -> set[str]:
    return {a["name"] for a in antwoord["data"]["actions"] if a["enabled"]}


@pytest.mark.unit
@pytest.mark.asyncio
class TestLezen:
    async def test_a_user_reads_the_setting_of_his_own_tenant(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(2, ["user"]), monkeypatch)

        antwoord = client.get(PAD)

        assert _aan(antwoord.json()) == {"make_payment"}

    async def test_every_action_carries_a_dutch_label(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["user"]), monkeypatch)

        acties = client.get(PAD).json()["data"]["actions"]

        assert all(a["label"] for a in acties) and len(acties) == 10


@pytest.mark.unit
@pytest.mark.asyncio
class TestWijzigen:
    async def test_an_administrator_changes_the_setting(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.put(PAD, json={"actions": ["send_payment_reminder"]})

        assert _aan(client.get(PAD).json()) == {"send_payment_reminder"}

    async def test_another_tenant_is_not_touched(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.models.rbac_models import Tenant

        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.put(PAD, json={"actions": []})

        twee = await db_session.get(Tenant, 2)
        await db_session.refresh(twee)
        assert twee is not None and twee.settings["four_eyes_actions"] == ["make_payment"]

    async def test_a_user_without_the_right_gets_403(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["user"]), monkeypatch)

        assert client.put(PAD, json={"actions": []}).status_code == 403

    async def test_an_unknown_action_is_refused(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, _ = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        assert client.put(PAD, json={"actions": ["drop_database"]}).status_code == 400

    async def test_a_change_is_written_to_the_audit_log(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _tenants(db_session)
        client, audit = _client(db_session, _gebruiker(1, ["admin"]), monkeypatch)

        client.put(PAD, json={"actions": ["make_payment"]})

        assert audit.await_args is not None
        assert audit.await_args.kwargs["event_type"] == "four_eyes_settings_changed"
