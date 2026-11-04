"""Acceptant ronde 3, N3: een beheerder op een geblokkeerd IP kan inloggen en deblokkeren.

Live gemeten: een beheerder met een geldig Bearer-token kreeg op `/api/v1/security/blocks` toch
`403 IP blocked`. `_is_admin_token` las de claims `roles`/`role`/`is_superuser`, en het token dat
de login uitgeeft bevat die niet (`email, exp, iat, jti, role_ids, scopes, sub, tenant_id`).

Echt in deze test: de volledige app (`register_all_routers`) achter de ECHTE SecurityMiddleware,
de ECHTE loginroute met wachtwoordcontrole en het token dat die uitgeeft, Postgres (netwerkpoort
5455) en Redis (`REDIS_URL`, eigen sleutelvoorvoegsel dat na afloop wordt opgeruimd). Er wordt
GEEN token met de hand gemaakt, behalve in de tegenproef die laat zien dat een zelfgemaakte
`role: admin`-claim niets oplevert.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.requires_redis]

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ADMIN_EMAIL = "admin@integration.test"
ADMIN_PASS = "AdminPass123!"
SCRIPT_PAD = Path(__file__).resolve().parents[3] / "scripts" / "seed_tweede_gebruiker.py"


def _ruim_op(voorvoegsel: str) -> None:
    import redis

    r = redis.Redis.from_url(REDIS_URL)
    for sleutel in r.scan_iter(match=f"{voorvoegsel}*"):
        r.delete(sleutel)
    r.close()


@pytest_asyncio.fixture
async def opstelling(
    integration_app: Any, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[dict[str, Any], None]:
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db
    from src.core.database.session import get_db_session
    from src.core.security import ip_reputation as ip_module
    from src.core.security.ip_reputation import IpReputation, IpReputationSettings
    from src.core.security.security_middleware import SecurityMiddleware

    monkeypatch.setenv("ENVIRONMENT", "test")
    voorvoegsel = f"n3test-{uuid.uuid4().hex[:8]}:"
    reputatie = IpReputation(IpReputationSettings(key_prefix=voorvoegsel), redis_url=REDIS_URL)
    # Dezelfde instantie voor de middleware EN voor de beheerroutes (`get_ip_reputation`).
    monkeypatch.setattr(ip_module, "_ip_reputation", reputatie)

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    overrides = {get_db: _db, api_get_db: _db, get_db_session: _db}
    integration_app.dependency_overrides.update(overrides)
    app = SecurityMiddleware(integration_app, enable_security=True, ip_reputation=reputatie)
    ip = f"203.0.113.{uuid.uuid4().int % 200 + 20}"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("10.0.0.5", 50000)),  # type: ignore[arg-type]
            base_url="http://test",
            headers={"X-Forwarded-For": ip},
        ) as client:
            await reputatie.block(ip, "test N3")
            assert await reputatie.is_blocked(ip)
            yield {"client": client, "ip": ip, "reputatie": reputatie, "db": postgres_session}
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)
        _ruim_op(voorvoegsel)


@pytest_asyncio.fixture
async def gecommitte_medewerker() -> AsyncGenerator[None, None]:
    from sqlalchemy import text

    from src.core.database.database import db_manager

    spec = importlib.util.spec_from_file_location("_seed_n3b", SCRIPT_PAD)
    assert spec is not None and spec.loader is not None
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    async with db_manager.get_session() as session:
        user_id = await seed.maak_tweede_gebruiker(
            session,
            tenant_id=1,
            email="medewerker-n3b@integration.test",
            password="MedewerkerN3bPass!",
        )
    yield
    async with db_manager.get_session() as session:
        for query in (
            "DELETE FROM account_lockouts WHERE user_id = :u",
            "DELETE FROM user_roles WHERE user_id = :u",
            "DELETE FROM users WHERE id = :u",
        ):
            await session.execute(text(query), {"u": user_id})
        await session.commit()


async def _login(client: AsyncClient, email: str, wachtwoord: str) -> Any:
    return await client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": wachtwoord, "grant_type": "password"},
    )


@pytest.mark.asyncio
class TestBeheerderOpGeblokkeerdIp:
    async def test_an_admin_logs_in_lists_the_blocks_and_unblocks(
        self, opstelling: dict[str, Any]
    ) -> None:
        client: AsyncClient = opstelling["client"]
        ip: str = opstelling["ip"]

        login = await _login(client, ADMIN_EMAIL, ADMIN_PASS)
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        client.cookies.clear()  # alleen het Bearer-token telt hieronder
        kop = {"Authorization": f"Bearer {token}"}

        blokkades = await client.get("/api/v1/security/blocks", headers=kop)
        assert blokkades.status_code == 200, blokkades.text

        vrij = await client.post(
            "/api/v1/security/unblock-ip", json={"ip_address": ip}, headers=kop
        )
        assert vrij.status_code == 200, vrij.text
        assert not await opstelling["reputatie"].is_blocked(ip)

    async def test_the_csrf_token_route_stays_reachable(self, opstelling: dict[str, Any]) -> None:
        antwoord = await opstelling["client"].get("/api/v1/auth/csrf-token")

        assert antwoord.status_code != 403, antwoord.text


@pytest.mark.asyncio
class TestGeenVrijstellingVoorAnderen:
    async def test_a_non_admin_with_the_right_password_gets_no_token(
        self, opstelling: dict[str, Any]
    ) -> None:
        spec = importlib.util.spec_from_file_location("_seed_n3", SCRIPT_PAD)
        assert spec is not None and spec.loader is not None
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        await seed.maak_tweede_gebruiker(
            opstelling["db"],
            tenant_id=1,
            email="medewerker-n3@integration.test",
            password="MedewerkerN3Pass!",
        )

        login = await _login(
            opstelling["client"], "medewerker-n3@integration.test", "MedewerkerN3Pass!"
        )

        assert login.status_code == 403, login.text
        assert "access_token" not in login.text
        assert "Retry-After" in login.headers

    async def test_a_wrong_admin_password_is_still_refused(
        self, opstelling: dict[str, Any]
    ) -> None:
        login = await _login(opstelling["client"], ADMIN_EMAIL, "FoutWachtwoord123!")

        assert login.status_code == 401, login.text

    async def test_a_self_made_admin_role_claim_gives_no_exemption(
        self, opstelling: dict[str, Any]
    ) -> None:
        from src.core.auth.jwt_handler import jwt_handler

        nep = jwt_handler.create_access_token(
            data={"sub": "aanvaller@klant.nl", "role": "admin", "roles": ["admin"],
                  "is_superuser": True, "tenant_id": 1}
        )

        antwoord = await opstelling["client"].get(
            "/api/v1/security/blocks", headers={"Authorization": f"Bearer {nep}"}
        )

        assert antwoord.status_code == 403
        assert antwoord.json().get("error") == "IP blocked"

    async def test_other_routes_stay_blocked_without_a_token(
        self, opstelling: dict[str, Any]
    ) -> None:
        antwoord = await opstelling["client"].get("/api/v1/receivables")

        assert antwoord.status_code == 403
        assert antwoord.json().get("error") == "IP blocked"

    async def test_a_real_token_of_a_non_admin_gives_no_exemption(
        self, gecommitte_medewerker: None, opstelling: dict[str, Any]
    ) -> None:
        # `gecommitte_medewerker` EERST: dan wordt hij pas opgeruimd nadat de testtransactie
        # (met haar slot op de gebruikersrij) is teruggedraaid.
        """Tegenproef voor de vrijstelling: een ECHT, geldig token, maar van een gewone gebruiker.
        Het token wordt opgehaald voordat het adres (opnieuw) geblokkeerd wordt.

        De gebruiker wordt ECHT gecommit (fixture `gecommitte_medewerker`): de middleware zoekt
        hem op in een eigen sessie, en een gebruiker die alleen in de testtransactie staat zou
        daar ontbreken -- dan slaagt deze test ook als de beheerderscontrole weg is."""
        client: AsyncClient = opstelling["client"]
        reputatie = opstelling["reputatie"]
        await reputatie.unblock(opstelling["ip"])
        login = await _login(client, "medewerker-n3b@integration.test", "MedewerkerN3bPass!")
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        client.cookies.clear()
        await reputatie.block(opstelling["ip"], "test N3 opnieuw")

        antwoord = await client.get(
            "/api/v1/receivables", headers={"Authorization": f"Bearer {token}"}
        )

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("error") == "IP blocked"
