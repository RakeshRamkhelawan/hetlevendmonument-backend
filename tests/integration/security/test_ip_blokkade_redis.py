"""IP-blokkade tegen een ECHTE Redis (plan nazorg, deel I punt b).

- twee app-instanties (twee middlewares, elk met een eigen IpReputation en eigen client),
  een Redis: een blokkade die de ene zet, ziet de andere ook;
- een blokkade vervalt in echte tijd (basisduur 1 seconde);
- Redis onbereikbaar: het verkeer gaat door.

Redis komt uit `REDIS_URL` (de testomgeving: redis://localhost:6380/0). Elke test gebruikt een
eigen sleutelvoorvoegsel en ruimt dat op, zodat een andere bouwer op dezelfde Redis niets merkt.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.auth.jwt_handler import jwt_handler
from src.core.security.ip_reputation import IpReputation, IpReputationSettings
from src.core.security.security_middleware import SecurityMiddleware

pytestmark = [pytest.mark.integration, pytest.mark.requires_redis]

AANVALLER = "203.0.113.77"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _token() -> str:
    return str(
        jwt_handler.create_access_token(
            data={"sub": "u@klant.nl", "user_id": 1, "role": "user", "tenant_id": 1}
        )
    )


def _app(reputatie: IpReputation) -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/items")
    async def items(id: str = "", q: str = "") -> dict[str, str]:
        return {"ok": "ja"}

    app.add_middleware(SecurityMiddleware, enable_security=True, ip_reputation=reputatie)
    # Een directe afzender die een vertrouwde proxy is: alleen dan telt X-Forwarded-For.
    return TestClient(app, client=("10.0.0.5", 50000))


def _get(client: TestClient, query: str) -> int:
    return client.get(
        f"/api/v1/items?{query}",
        headers={"X-Forwarded-For": AANVALLER, "Authorization": f"Bearer {_token()}"},
    ).status_code


def _ruim_op(voorvoegsel: str) -> None:
    import redis

    r = redis.Redis.from_url(REDIS_URL)
    for sleutel in r.scan_iter(match=f"{voorvoegsel}*"):
        r.delete(sleutel)
    r.close()


@pytest.fixture
def voorvoegsel(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    waarde = f"sectest-{uuid.uuid4().hex[:8]}:"
    yield waarde
    _ruim_op(waarde)


def _instellingen(voorvoegsel: str, **extra: Any) -> IpReputationSettings:
    basis: dict[str, Any] = {"threshold": 9, "sql_signal_points": 3, "key_prefix": voorvoegsel}
    basis.update(extra)
    return IpReputationSettings(**basis)


def test_two_app_instances_see_the_same_block(voorvoegsel: str) -> None:
    instellingen = _instellingen(voorvoegsel)
    eerste = _app(IpReputation(instellingen, redis_url=REDIS_URL))
    tweede = _app(IpReputation(instellingen, redis_url=REDIS_URL))

    assert _get(tweede, "q=hallo") == 200
    assert [_get(eerste, "id=1%20OR%201=1") for _ in range(3)] == [200, 200, 403]
    # De tweede instantie heeft zelf niets gezien, en weigert toch.
    assert _get(tweede, "q=hallo") == 403


def test_the_score_from_two_instances_adds_up(voorvoegsel: str) -> None:
    instellingen = _instellingen(voorvoegsel)
    eerste = _app(IpReputation(instellingen, redis_url=REDIS_URL))
    tweede = _app(IpReputation(instellingen, redis_url=REDIS_URL))
    assert _get(eerste, "id=1%20OR%201=1") == 200
    assert _get(tweede, "id=1%20OR%201=1") == 200
    assert _get(eerste, "id=1%20OR%201=1") == 403


def test_the_block_expires_in_real_time(voorvoegsel: str) -> None:
    client = _app(
        IpReputation(_instellingen(voorvoegsel, block_base_seconds=1), redis_url=REDIS_URL)
    )
    for _ in range(3):
        _get(client, "id=1%20OR%201=1")
    assert _get(client, "q=hallo") == 403
    time.sleep(2.2)
    assert _get(client, "q=hallo") == 200


def test_unblock_from_one_instance_frees_the_ip_everywhere(voorvoegsel: str) -> None:
    instellingen = _instellingen(voorvoegsel)
    reputatie = IpReputation(instellingen, redis_url=REDIS_URL)
    client = _app(IpReputation(instellingen, redis_url=REDIS_URL))
    for _ in range(3):
        _get(client, "id=1%20OR%201=1")
    assert _get(client, "q=hallo") == 403
    assert asyncio.run(reputatie.unblock(AANVALLER)) is True
    assert _get(client, "q=hallo") == 200


def test_after_an_admin_unblock_the_next_block_has_the_base_duration(voorvoegsel: str) -> None:
    """B4-1: deblokkeren wist ook de strikes; een nieuwe blokkade duurt weer de basisduur."""
    instellingen = _instellingen(voorvoegsel, block_base_seconds=900)
    reputatie = IpReputation(instellingen, redis_url=REDIS_URL)
    beheer = IpReputation(instellingen, redis_url=REDIS_URL)
    client = _app(reputatie)

    for _ in range(3):
        _get(client, "id=1%20OR%201=1")
    assert _get(client, "q=hallo") == 403
    assert 890 <= (asyncio.run(beheer.block_seconds_left(AANVALLER)) or 0) <= 900

    assert asyncio.run(beheer.unblock(AANVALLER)) is True
    assert _get(client, "q=hallo") == 200

    for _ in range(3):
        _get(client, "id=1%20OR%201=1")
    assert _get(client, "q=hallo") == 403
    assert 890 <= (asyncio.run(beheer.block_seconds_left(AANVALLER)) or 0) <= 900


def test_traffic_passes_when_redis_is_unreachable(
    voorvoegsel: str, caplog: pytest.LogCaptureFixture
) -> None:
    client = _app(
        IpReputation(_instellingen(voorvoegsel), redis_url="redis://127.0.0.1:6399/0")
    )
    assert [_get(client, "id=1%20OR%201=1") for _ in range(5)] == [200] * 5
    assert "Redis niet bereikbaar" in caplog.text
