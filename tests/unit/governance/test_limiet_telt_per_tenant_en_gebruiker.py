"""Een limiet telt per tenant EN gebruiker, niet per ingress-adres.

Brief 2026-10-25 (rate limit faalt dicht), besluit regie 2026-10-26. De sleutel van de limiet kwam
uit `request.state.user` en, als dat ontbrak, uit `request.client.host`. `request.state.user` werd
in heel `src/` alleen door de bonnen-dependency gezet; voor elke andere limietroute was de sleutel
dus ingress-adres plus pad, en deelden alle klanten achter dezelfde ingress een emmer. Zodra de
limiet op 38 routes echt gaat werken, zou een klant de andere klanten buitensluiten.

`TenantMiddleware` zet na het controleren van het JWT wel `request.state.tenant_id` en
`request.state.user_id`. Deze tests lopen over de ECHTE middleware, een echt JWT en de echte
koppelroute `GET /integrations/connections` (60 per minuut). Alle verzoeken komen van hetzelfde
clientadres (de TestClient), dus een emmer per tenant en gebruiker is het enige dat ze scheidt.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from src.core.activepieces.service import get_activepieces_service
from src.core.api.v1.activepieces import connections_router
from src.core.auth.account_status import AccountStatus
from src.core.auth.api_deps import get_current_user
from src.core.auth.jwt_handler import jwt_handler
from src.core.middleware.tenant_middleware import TenantMiddleware
from src.core.shared import rate_limiter as shared_limiter

pytestmark = pytest.mark.unit

LIJST = "/integrations/connections"
MAXIMUM = 60  # integration_read_limit


# De `sub` van een token is het numerieke id; de limiet telt op dat id (brief 2026-10-27).
_ID_VAN = {
    "gebruiker-a": "11",
    "gebruiker-b": "12",
    "collega-a": "13",
    "gebruiker-x": "14",
    "jan": "15",
}


def _token(tenant_id: int, gebruiker: str) -> dict[str, str]:
    token = jwt_handler.create_access_token(
        {
            "sub": _ID_VAN[gebruiker],
            "tenant_id": tenant_id,
            "email": f"{gebruiker}@x.test",
            "roles": ["admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    shared_limiter._rate_limiter._requests.clear()
    dienst = MagicMock()
    dienst.list_connections = AsyncMock(return_value=[])
    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(connections_router.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, tenant_id=1)
    app.dependency_overrides[get_activepieces_service] = lambda: dienst
    with patch(
        "src.core.auth.account_status.haal_account_status",
        new=AsyncMock(return_value=AccountStatus.ACTIEF),
    ):
        yield TestClient(app)
    shared_limiter._rate_limiter._requests.clear()


def _uitputten(client: TestClient, kopregels: dict[str, str]) -> int:
    """Doe het maximum aantal aanroepen en geef de status van de eerstvolgende."""
    for _ in range(MAXIMUM):
        client.get(LIJST, headers=kopregels)
    return client.get(LIJST, headers=kopregels).status_code


def test_de_ene_tenant_op_429_laat_de_andere_tenant_met_rust(client: TestClient) -> None:
    status_a = _uitputten(client, _token(1, "gebruiker-a"))

    status_b = client.get(LIJST, headers=_token(2, "gebruiker-b")).status_code

    assert (status_a, status_b) == (429, 200)


def test_twee_gebruikers_van_dezelfde_tenant_hebben_elk_een_eigen_emmer(
    client: TestClient,
) -> None:
    status_eerste = _uitputten(client, _token(1, "gebruiker-a"))

    status_tweede = client.get(LIJST, headers=_token(1, "collega-a")).status_code

    assert (status_eerste, status_tweede) == (429, 200)


def test_dezelfde_gebruiker_blijft_in_zijn_eigen_emmer(client: TestClient) -> None:
    """De andere kant op: de limiet werkt nog steeds voor wie hem overschrijdt."""
    kopregels = _token(1, "gebruiker-a")

    assert _uitputten(client, kopregels) == 429


def test_de_eerste_zestig_aanroepen_van_een_gebruiker_zijn_toegestaan(client: TestClient) -> None:
    kopregels = _token(1, "gebruiker-a")

    statussen = [client.get(LIJST, headers=kopregels).status_code for _ in range(MAXIMUM)]

    assert set(statussen) == {200}


def test_de_sleutel_noemt_tenant_en_gebruiker_en_niet_het_ip() -> None:
    request = MagicMock()
    request.state = SimpleNamespace(tenant_id=7, limiet_gebruiker="u9")
    request.client = SimpleNamespace(host="10.0.0.5")

    assert shared_limiter._get_user_id_from_request(request) == "7:u9"


def test_zonder_token_valt_de_sleutel_terug_op_het_clientadres() -> None:
    request = MagicMock()
    request.state = SimpleNamespace()
    request.client = SimpleNamespace(host="203.0.113.4")

    assert shared_limiter._get_user_id_from_request(request) == "203.0.113.4"


def test_een_state_met_alleen_een_tenant_en_geen_gebruiker_wordt_geweigerd() -> None:
    """Een halve identiteit is geen identiteit, en geen gedeelde emmer: een 401 (brief 2026-10-27)."""
    request = MagicMock()
    request.state = SimpleNamespace(tenant_id=7)
    request.client = SimpleNamespace(host="203.0.113.4")

    with pytest.raises(HTTPException) as fout:
        shared_limiter._get_user_id_from_request(request)

    assert fout.value.status_code == 401


def test_agent_execute_limit_krijgt_tenant_en_gebruiker_uit_het_token(client: TestClient) -> None:
    """H2 van de security-review: de sleutel is NIET `agent_execute:None:None`.

    `agent_execute_limit` leest `request.state.tenant_id` en `request.state.user_id`; die zet
    `TenantMiddleware` uit het JWT. Gemeten over de echte middleware.
    """
    from src.core.governance import rate_limiter as governance_limiter

    router = APIRouter()

    @router.post("/uitvoeren")
    @governance_limiter.agent_execute_limit
    async def uitvoeren(request: Request) -> dict[str, str]:
        return {"ok": "ja"}

    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(router)
    check = AsyncMock()
    with (
        patch(
            "src.core.auth.account_status.haal_account_status",
            new=AsyncMock(return_value=AccountStatus.ACTIEF),
        ),
        patch.object(governance_limiter, "check_agent_execute_limit", new=check),
    ):
        TestClient(app).post("/uitvoeren", headers=_token(5, "gebruiker-x"))

    assert check.await_args is not None and check.await_args.args == ("5", "u14")


def test_dezelfde_gebruikersnaam_in_twee_tenants_deelt_geen_emmer(client: TestClient) -> None:
    status_eerste = _uitputten(client, _token(1, "jan"))

    status_tweede = client.get(LIJST, headers=_token(2, "jan")).status_code

    assert (status_eerste, status_tweede) == (429, 200)
