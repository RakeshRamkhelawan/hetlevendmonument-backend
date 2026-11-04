"""De beheerroutes voor IP-blokkades: alleen een beheerder, en ze werken op de IP-reputatie.

`/api/v1/security/blocks`, `/block-ip` en `/unblock-ip` (plan nazorg, deel I punt b). Ze
werkten op een `set` in het geheugen van een proces; nu op Redis, voor alle workers tegelijk.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.auth.auth_service import UserResponse
from src.core.security.ip_reputation import IpReputation, IpReputationSettings, RedisLike
from tests.fixtures.nep_redis import NepRedis

IP = "203.0.113.50"


@pytest.fixture
def reputatie(monkeypatch: pytest.MonkeyPatch) -> Iterator[IpReputation]:
    from src.core.api.v1.security import management_router

    rep = IpReputation(IpReputationSettings(threshold=3), client=cast(RedisLike, NepRedis()))
    monkeypatch.setattr(management_router, "get_ip_reputation", lambda: rep)
    yield rep


def _client(*, beheerder: bool) -> TestClient:
    from src.core.api.v1.security.router import router
    from src.core.auth import dependencies as auth_deps

    gebruiker = UserResponse(
        id=3, email="b@klant.nl", tenant_id=1, roles=["admin"] if beheerder else ["user"]
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[auth_deps.get_current_user] = lambda: gebruiker
    app.dependency_overrides[auth_deps.get_current_user_dependency] = lambda: gebruiker

    for route in app.routes:
        for dep in getattr(getattr(route, "dependant", None), "dependencies", []) or []:
            naam = getattr(dep.call, "__name__", "")
            if naam == "scope_checker":
                app.dependency_overrides[dep.call] = lambda: 3
    return TestClient(app)


@pytest.mark.unit
async def test_an_admin_can_unblock_an_ip(reputatie: IpReputation) -> None:
    await reputatie.record(IP, 3, "sql_injection_signal")
    client = _client(beheerder=True)
    assert [b["ip_address"] for b in client.get("/api/v1/security/blocks").json()] == [IP]
    response = client.post("/api/v1/security/unblock-ip", json={"ip_address": IP})
    assert response.status_code == 200, response.text
    assert "has been unblocked" in response.json()["message"]
    assert await reputatie.is_blocked(IP) is False


@pytest.mark.unit
async def test_a_non_admin_cannot_unblock(reputatie: IpReputation) -> None:
    await reputatie.record(IP, 3, "sql_injection_signal")
    response = _client(beheerder=False).post(
        "/api/v1/security/unblock-ip", json={"ip_address": IP}
    )
    assert response.status_code == 403
    assert await reputatie.is_blocked(IP) is True


@pytest.mark.unit
def test_an_invalid_ip_is_refused(reputatie: IpReputation) -> None:
    response = _client(beheerder=True).post(
        "/api/v1/security/unblock-ip", json={"ip_address": "geen-ip"}
    )
    assert response.status_code == 400
