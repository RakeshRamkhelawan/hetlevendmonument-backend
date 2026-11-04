"""De IP-blokkade in de SecurityMiddleware (plan nazorg, deel I punten a en b).

Wat hier vastligt:
- gewone invoer (`?color=#fff`, `?q=update address`, `?sort=--date`) blokkeert niet, ook niet
  na veel herhalingen;
- herhaalde echte injectie wel, en de aanvraag die de drempel passeert krijgt zelf 403;
- een blokkade geeft 403 met Retry-After, geen 429;
- de allowlist en een beheerder met een geldig token worden nooit geblokkeerd, een ongeldig
  token geeft geen vrijstelling;
- Redis uit: het verkeer gaat door.

De nep-Redis staat in `test_ip_reputatie.py`. Echte Redis, twee app-instanties en verlopen in
echte tijd: `tests/integration/security/test_ip_blokkade_redis.py`.
"""

from __future__ import annotations

import functools
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.auth.jwt_handler import jwt_handler
from src.core.security.ip_reputation import IpReputation, IpReputationSettings
from src.core.security.security_middleware import SecurityMiddleware
from tests.fixtures.nep_redis import KapotteRedis, NepRedis

AANVALLER = "203.0.113.9"


@functools.lru_cache(maxsize=None)
def _token(rol: str) -> str:
    return str(
        jwt_handler.create_access_token(
            data={"sub": f"{rol}@klant.nl", "user_id": 1, "role": rol, "tenant_id": 1}
        )
    )


def _app(reputatie: IpReputation) -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/items")
    async def items(q: str = "", color: str = "", sort: str = "", id: str = "") -> dict[str, str]:
        return {"ok": "ja"}

    app.add_middleware(SecurityMiddleware, enable_security=True, ip_reputation=reputatie)
    # Een directe afzender die een vertrouwde proxy is: alleen dan telt X-Forwarded-For.
    return TestClient(app, client=("10.0.0.5", 50000))


def _reputatie(redis: Any, **instellingen: Any) -> IpReputation:
    basis: dict[str, Any] = {"threshold": 15, "sql_signal_points": 3}
    basis.update(instellingen)
    return IpReputation(IpReputationSettings(**basis), client=redis)


def _get(client: TestClient, query: str, *, ip: str = AANVALLER, rol: str = "user") -> Any:
    return client.get(
        f"/api/v1/items?{query}",
        headers={"X-Forwarded-For": ip, "Authorization": f"Bearer {_token(rol)}"},
    )


#: Wie de beheerderscontrole als beheerder herkent. Die controle zoekt de gebruiker van het
#: token op in de database (acceptant ronde 3, N3) en hoort dus niet in een unittest; hier
#: staat ze vervangen door deze lijst. Het ECHTE gedrag -- een token uit de echte login, een
#: zelfgemaakte `role: admin`-claim die niets oplevert -- meet
#: `tests/integration/security/test_beheerder_ontsnapt_aan_de_ip_blokkade.py`.
BEHEERDERS: set[str] = set()


@pytest.fixture(autouse=True)
def _testomgeving(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    BEHEERDERS.clear()

    async def _is_admin_token(self: SecurityMiddleware, request: Any) -> bool:
        return request.headers.get("Authorization", "") in BEHEERDERS

    monkeypatch.setattr(SecurityMiddleware, "_is_admin_token", _is_admin_token)


@pytest.mark.unit
class TestGewoneInvoerBlokkeertNiet:
    @pytest.mark.parametrize("query", ["color=%23fff", "q=update%20address", "sort=--date"])
    def test_ordinary_input_never_blocks_even_when_repeated(self, query: str) -> None:
        redis = NepRedis()
        client = _app(_reputatie(redis))
        for _ in range(20):
            assert _get(client, query).status_code == 200
        assert not [k for k in redis.data if ":block:" in k]


@pytest.mark.unit
class TestHerhaaldeInjectie:
    def test_the_request_that_crosses_the_threshold_gets_403_itself(self) -> None:
        client = _app(_reputatie(NepRedis()))
        codes = [_get(client, "id=1%20OR%201=1").status_code for _ in range(5)]
        assert codes == [200, 200, 200, 200, 403]

    def test_after_the_block_even_ordinary_requests_get_403_with_retry_after(self) -> None:
        client = _app(_reputatie(NepRedis(), block_base_seconds=900))
        for _ in range(5):
            _get(client, "id=1%20OR%201=1")
        response = _get(client, "q=hallo")
        assert response.status_code == 403
        assert response.headers["Retry-After"] == "900"

    def test_another_ip_is_not_blocked(self) -> None:
        client = _app(_reputatie(NepRedis()))
        for _ in range(5):
            _get(client, "id=1%20OR%201=1")
        assert _get(client, "q=hallo", ip="198.51.100.4").status_code == 200

    def test_the_block_expires(self) -> None:
        redis = NepRedis()
        client = _app(_reputatie(redis, block_base_seconds=900))
        for _ in range(5):
            _get(client, "id=1%20OR%201=1")
        redis.nu += 901
        assert _get(client, "q=hallo").status_code == 200


@pytest.mark.unit
class TestVrijstellingen:
    def test_an_admin_with_a_valid_token_is_never_blocked(self) -> None:
        BEHEERDERS.add(f"Bearer {_token('admin')}")
        client = _app(_reputatie(NepRedis()))
        codes = [_get(client, "id=1%20OR%201=1", rol="admin").status_code for _ in range(10)]
        assert set(codes) == {200}

    def test_an_invalid_token_gives_no_exemption(self) -> None:
        client = _app(_reputatie(NepRedis()))
        for _ in range(5):
            _get(client, "id=1%20OR%201=1")
        response = client.get(
            "/api/v1/items?q=hallo",
            headers={"X-Forwarded-For": AANVALLER, "Authorization": "Bearer nep.admin.token"},
        )
        assert response.status_code == 403

    def test_an_address_on_the_allowlist_is_never_blocked(self) -> None:
        client = _app(_reputatie(NepRedis(), exempt_cidrs=("203.0.113.0/24",)))
        codes = [_get(client, "id=1%20OR%201=1").status_code for _ in range(10)]
        assert set(codes) == {200}


@pytest.mark.unit
class TestRedisUit:
    def test_traffic_passes_when_redis_is_down(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _app(_reputatie(KapotteRedis()))
        codes = [_get(client, "id=1%20OR%201=1").status_code for _ in range(10)]
        assert set(codes) == {200}
        assert "Redis niet bereikbaar" in caplog.text
