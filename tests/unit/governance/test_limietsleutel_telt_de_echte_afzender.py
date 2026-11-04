"""De sleutel van een limiet telt de echte afzender, de route en de gebruiker -- en faalt dicht.

Brief 2026-10-27 (rate-limit nazorg). Gemeten op `4e6f0ef7`:

- M1: `_ip_key` nam de EERSTE waarde uit X-Forwarded-For. Die stuurt de client zelf mee; de proxy
  plakt het echte adres er RECHTS achter. Per verzoek een andere eerste waarde = per verzoek een
  nieuwe emmer: de limieten op inloggen en portaal waren te omzeilen.
- M2: het ingevulde pad zat in de sleutel; `/x/1` en `/x/2` kregen elk een eigen emmer.
- `sub`: het wachtwoordpad zet het e-mailadres in `sub`, de andere paden het id. Eenzelfde gebruiker
  kreeg twee emmers.
- M3: een gedecoreerde functie zonder Request liep ongelimiteerd door.
- L1: de controle accepteerde elke klasse die `Request` heet.

Elke test hier heeft een tegenhanger die de andere kant bewaakt: een legitiem verschillend adres,
verschillende route of verschillende gebruiker houdt een EIGEN emmer. Zonder die helft is "alles in
een emmer" een geldige oplossing.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from src.core.auth.account_status import AccountStatus
from src.core.auth.jwt_handler import jwt_handler
from src.core.governance import rate_limiter as governance_limiter
from src.core.middleware.tenant_middleware import TenantMiddleware
from src.core.shared import rate_limiter as shared_limiter
from src.core.shared.limiet_sleutel import route_sleutel

pytestmark = pytest.mark.unit

PROXY = ("10.0.0.5", 5000)  # de ingress: een prive-adres, dus een vertrouwde proxy
ECHT_A = "203.0.113.9"
ECHT_B = "203.0.113.77"


@pytest.fixture(autouse=True)
def _schone_limiter() -> Iterator[None]:
    shared_limiter._rate_limiter._requests.clear()
    yield
    shared_limiter._rate_limiter._requests.clear()


def _request(
    *, client: tuple[str, int] | None, xff: str | None = None, route_pad: str | None = None
) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    scope: dict[str, object] = {"type": "http", "headers": headers, "path": "/ingevuld/9"}
    if client is not None:
        scope["client"] = client
    if route_pad is not None:
        scope["route"] = SimpleNamespace(path=route_pad)
    return Request(scope=scope)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- M1: het adres


def _portaalapp() -> FastAPI:
    router = APIRouter()

    @router.get("/portaal")
    @governance_limiter.portal_auth_limit  # 5 per minuut, sleutel op het adres
    async def portaal(request: Request) -> dict[str, str]:
        return {"ok": "ja"}

    app = FastAPI()
    app.include_router(router)
    return app


def _aanroepen(client: TestClient, kopregels: list[str]) -> list[int]:
    return [client.get("/portaal", headers={"X-Forwarded-For": k}).status_code for k in kopregels]


def test_een_zelf_meegestuurde_linkse_waarde_geeft_geen_nieuwe_emmer() -> None:
    client = TestClient(_portaalapp(), client=PROXY)
    # De client bedenkt per verzoek een ander eerste adres; de proxy plakt het echte adres rechts.
    kopregels = [f"198.51.100.{i}, {ECHT_A}" for i in range(6)]

    statussen = _aanroepen(client, kopregels)

    assert statussen == [200, 200, 200, 200, 200, 429]


def test_twee_echte_adressen_hebben_elk_een_eigen_emmer() -> None:
    client = TestClient(_portaalapp(), client=PROXY)
    _aanroepen(client, [f"198.51.100.1, {ECHT_A}"] * 6)

    status_b = _aanroepen(client, [f"198.51.100.1, {ECHT_B}"])

    assert status_b == [200]


def test_de_meest_rechtse_waarde_die_geen_vertrouwde_proxy_is_telt() -> None:
    request = _request(client=PROXY, xff=f"6.6.6.6, {ECHT_A}, 10.1.1.1")

    assert governance_limiter._ip_key(request) == f"ip:{ECHT_A}"


def test_een_zelf_meegestuurde_waarde_verandert_het_adres_niet() -> None:
    zonder = _request(client=PROXY, xff=ECHT_A)
    met = _request(client=PROXY, xff=f"6.6.6.6, {ECHT_A}")

    assert governance_limiter._ip_key(zonder) == governance_limiter._ip_key(met)


def test_een_xff_van_een_openbare_afzender_wordt_genegeerd() -> None:
    """GHSA-c2r5-cfqr-c553: wie de proxy omzeilt, kiest zijn adres niet."""
    request = _request(client=("198.51.100.4", 4000), xff="6.6.6.6")

    assert governance_limiter._ip_key(request) == "ip:198.51.100.4"


def test_een_xff_met_alleen_vertrouwde_waarden_valt_terug_op_de_verbinding() -> None:
    request = _request(client=PROXY, xff="10.2.2.2, 10.3.3.3")

    assert governance_limiter._ip_key(request) == "ip:10.0.0.5"


def test_een_onbruikbare_xff_waarde_valt_terug_op_de_verbinding() -> None:
    request = _request(client=PROXY, xff="geen-adres")

    assert governance_limiter._ip_key(request) == "ip:10.0.0.5"


def test_een_onbruikbare_waarde_rechts_in_de_keten_gaat_niet_door_naar_links() -> None:
    """Rechts is wat de proxy schreef; is dat onbruikbaar, dan telt wat links staat niet."""
    request = _request(client=PROXY, xff="6.6.6.6, geen-adres")

    assert governance_limiter._ip_key(request) == "ip:10.0.0.5"


def test_een_documentatieadres_telt_niet_als_vertrouwde_proxy() -> None:
    """`ipaddress.is_private` telt 203.0.113.0/24 als prive; een afzender daar is geen proxy."""
    request = _request(client=("203.0.113.9", 4000), xff="6.6.6.6")

    assert governance_limiter._ip_key(request) == "ip:203.0.113.9"


# --------------------------------------------------------------------------- M2: de route


def _routeapp(maximum: int = 2) -> FastAPI:
    router = APIRouter()
    limiet = shared_limiter.privacy_rate_limit(max_requests=maximum, window_seconds=60)

    @router.get("/x/{item_id}")
    @limiet
    async def een(request: Request, item_id: int) -> dict[str, int]:
        return {"id": item_id}

    @router.get("/y/{item_id}")
    @limiet
    async def twee(request: Request, item_id: int) -> dict[str, int]:
        return {"id": item_id}

    app = FastAPI()
    app.include_router(router)
    return app


def test_een_ander_id_in_het_pad_wisselt_niet_van_emmer() -> None:
    client = TestClient(_routeapp())

    statussen = [client.get(f"/x/{i}").status_code for i in (1, 2, 3)]

    assert statussen == [200, 200, 429]


def test_een_andere_route_heeft_een_eigen_emmer() -> None:
    client = TestClient(_routeapp())
    for i in (1, 2, 3):
        client.get(f"/x/{i}")

    assert client.get("/y/1").status_code == 200


def test_de_routesleutel_is_het_sjabloon_en_niet_het_ingevulde_pad() -> None:
    request = _request(client=None, route_pad="/x/{item_id}")

    assert route_sleutel(request) == "/x/{item_id}"


def test_een_verzoek_zonder_gevonden_route_valt_terug_op_een_vaste_waarde() -> None:
    een = _request(client=None)
    ander = _request(client=None)
    ander.scope["path"] = "/heel/ander/pad/1"

    assert route_sleutel(een) == route_sleutel(ander)


# --------------------------------------------------------------------------- sub: het gebruikers-id

LIJST = "/lijst"
MAXIMUM = 5


def _token(sub: str, tenant_id: int = 1) -> dict[str, str]:
    token = jwt_handler.create_access_token(
        {"sub": sub, "tenant_id": tenant_id, "email": "jan@x.test", "roles": ["admin"]}
    )
    return {"Authorization": f"Bearer {token}"}


def _gebruikersapp() -> TestClient:
    router = APIRouter()

    @router.get(LIJST)
    @shared_limiter.privacy_rate_limit(max_requests=MAXIMUM, window_seconds=60)
    async def lijst(request: Request) -> dict[str, str]:
        return {"ok": "ja"}

    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def e_mailadres_hoort_bij() -> Iterator[dict[str, int]]:
    """De opzoeking van een e-mailadres naar een id (de database), per test in te stellen."""
    bekend: dict[str, int] = {}

    async def zoek(email: str, tenant_id: int) -> int | None:
        return bekend.get(email)

    with (
        patch(
            "src.core.auth.account_status.haal_account_status",
            new=AsyncMock(return_value=AccountStatus.ACTIEF),
        ),
        patch("src.core.auth.account_status._zoek_id_bij_email", new=zoek),
    ):
        yield bekend


def _uitputten(client: TestClient, kopregels: dict[str, str]) -> int:
    for _ in range(MAXIMUM):
        client.get(LIJST, headers=kopregels)
    return client.get(LIJST, headers=kopregels).status_code


def test_een_token_met_een_e_mail_sub_en_een_met_een_id_sub_delen_een_emmer(
    e_mailadres_hoort_bij: dict[str, int],
) -> None:
    e_mailadres_hoort_bij["jan@x.test"] = 7
    client = _gebruikersapp()
    _uitputten(client, _token("7"))

    status = client.get(LIJST, headers=_token("jan@x.test")).status_code

    assert status == 429


def test_een_andere_gebruiker_heeft_een_eigen_emmer(
    e_mailadres_hoort_bij: dict[str, int],
) -> None:
    e_mailadres_hoort_bij["jan@x.test"] = 7
    client = _gebruikersapp()
    _uitputten(client, _token("7"))

    status = client.get(LIJST, headers=_token("8")).status_code

    assert status == 200


def test_hetzelfde_id_in_een_andere_tenant_heeft_een_eigen_emmer(
    e_mailadres_hoort_bij: dict[str, int],
) -> None:
    client = _gebruikersapp()
    _uitputten(client, _token("7", tenant_id=1))

    status = client.get(LIJST, headers=_token("7", tenant_id=2)).status_code

    assert status == 200


def test_een_gebruiker_waarvan_het_id_niet_te_bepalen_is_wordt_geweigerd(
    e_mailadres_hoort_bij: dict[str, int],
) -> None:
    """Geen `anon`-emmer en geen gedeelde emmer: een route die inloggen vereist weigert."""
    client = _gebruikersapp()

    status = client.get(LIJST, headers=_token("onbekend@x.test")).status_code

    assert status == 401


def test_de_sleutel_van_een_gebruikersobject_is_tenant_en_numeriek_id() -> None:
    request = _request(client=None)
    request.state.user = SimpleNamespace(id=7, tenant_id=3)

    assert shared_limiter._get_user_id_from_request(request) == "3:u7"


def test_een_ruwe_sub_zonder_vastgesteld_id_wordt_geen_sleutel() -> None:
    request = _request(client=None)
    request.state.tenant_id = 3
    request.state.user_id = "jan@x.test"

    with pytest.raises(HTTPException) as fout:
        shared_limiter._get_user_id_from_request(request)

    assert fout.value.status_code == 401


# --------------------------------------------------------------------------- M3: faalt dicht


@pytest.mark.parametrize(
    "decorator",
    [
        shared_limiter.privacy_rate_limit(max_requests=5, window_seconds=60),
        governance_limiter.cva_chat_limit,
        governance_limiter.copilot_turn_limit(),
        governance_limiter.agent_execute_limit,
    ],
    ids=["privacy_rate_limit", "cva_chat_limit", "copilot_turn_limit", "agent_execute_limit"],
)
async def test_een_aanroep_zonder_request_geeft_een_fout_en_voert_niets_uit(
    decorator: object,
) -> None:
    uitgevoerd: list[str] = []

    async def inhoud(request: Request) -> None:
        uitgevoerd.append("ja")

    gedecoreerd = decorator(inhoud)  # type: ignore[operator]

    with pytest.raises(RuntimeError, match="Request"):
        await gedecoreerd()
    assert uitgevoerd == []


async def test_een_aanroep_met_request_wordt_wel_uitgevoerd() -> None:
    async def inhoud(request: Request) -> str:
        return "uitgevoerd"

    gedecoreerd = shared_limiter.privacy_rate_limit(max_requests=5, window_seconds=60)(inhoud)

    assert await gedecoreerd(_request(client=("203.0.113.1", 1))) == "uitgevoerd"


# --------------------------------------------------------------------------- L1: echt Request


def _functie_met(request_klasse: type, *, als_string: bool) -> object:
    """Een functie waarvan de `Request` in zijn eigen module naar `request_klasse` wijst."""
    omgeving: dict[str, object] = {"Request": request_klasse}
    kop = "from __future__ import annotations\n" if als_string else ""
    exec(kop + "async def route(request: Request) -> None:\n    return None\n", omgeving)  # noqa: S102
    return omgeving["route"]


class Request_van_iemand_anders:  # noqa: N801 - de naam is het punt van de test
    pass


Request_van_iemand_anders.__name__ = "Request"


@pytest.mark.parametrize("als_string", [True, False], ids=["string", "klasse"])
def test_een_eigen_klasse_die_request_heet_wordt_bij_het_laden_geweigerd(
    als_string: bool,
) -> None:
    route = _functie_met(Request_van_iemand_anders, als_string=als_string)

    with pytest.raises(TypeError, match="Request"):
        shared_limiter.vereis_request_parameter(route, "proef")  # type: ignore[arg-type]


@pytest.mark.parametrize("als_string", [True, False], ids=["string", "klasse"])
def test_de_echte_request_wordt_geaccepteerd(als_string: bool) -> None:
    route = _functie_met(Request, als_string=als_string)

    assert shared_limiter.vereis_request_parameter(route, "proef") is None  # type: ignore[arg-type]


def test_een_subklasse_van_de_echte_request_wordt_geaccepteerd() -> None:
    class MijnRequest(Request):
        pass

    route = _functie_met(MijnRequest, als_string=False)

    assert shared_limiter.vereis_request_parameter(route, "proef") is None  # type: ignore[arg-type]


def test_een_string_annotatie_die_nergens_naar_wijst_wordt_geweigerd() -> None:
    omgeving: dict[str, object] = {}
    exec(  # noqa: S102
        "from __future__ import annotations\nasync def route(request: Request) -> None: ...\n",
        omgeving,
    )

    with pytest.raises(TypeError, match="Request"):
        shared_limiter.vereis_request_parameter(omgeving["route"], "proef")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- gebruikers_id_uit_sub


@pytest.fixture
def lege_id_cache() -> Iterator[None]:
    from src.core.auth import account_status

    account_status._ID_BIJ_EMAIL.clear()
    yield
    account_status._ID_BIJ_EMAIL.clear()


async def test_een_portaal_id_en_een_medewerker_id_delen_geen_emmer() -> None:
    from src.core.auth.account_status import gebruikers_id_uit_sub

    portaal = await gebruikers_id_uit_sub("7", 1, portal=True)
    medewerker = await gebruikers_id_uit_sub("7", 1, portal=False)

    assert (portaal, medewerker) == ("p7", "u7")


async def test_een_portaaltoken_met_een_e_mail_sub_heeft_geen_id() -> None:
    from src.core.auth.account_status import gebruikers_id_uit_sub

    assert await gebruikers_id_uit_sub("jan@x.test", 1, portal=True) is None


async def test_een_te_lange_numerieke_sub_heeft_geen_id() -> None:
    from src.core.auth.account_status import gebruikers_id_uit_sub

    assert await gebruikers_id_uit_sub("1" * 10, 1) is None


async def test_een_databasefout_bij_het_opzoeken_geeft_geen_id(lege_id_cache: None) -> None:
    from src.core.auth.account_status import gebruikers_id_uit_sub

    with patch(
        "src.core.auth.account_status._zoek_id_bij_email",
        new=AsyncMock(side_effect=RuntimeError("Database not initialized")),
    ):
        assert await gebruikers_id_uit_sub("jan@x.test", 1) is None


async def test_een_e_mailadres_wordt_binnen_de_geldigheid_een_keer_opgezocht(
    lege_id_cache: None,
) -> None:
    from src.core.auth.account_status import gebruikers_id_uit_sub

    zoek = AsyncMock(return_value=7)
    with patch("src.core.auth.account_status._zoek_id_bij_email", new=zoek):
        eerste = await gebruikers_id_uit_sub("jan@x.test", 1)
        tweede = await gebruikers_id_uit_sub("jan@x.test", 1)

    assert (eerste, tweede, zoek.await_count) == ("u7", "u7", 1)


async def test_een_verlopen_vermelding_wordt_opnieuw_opgezocht(lege_id_cache: None) -> None:
    from src.core.auth import account_status

    zoek = AsyncMock(return_value=7)
    tijd = iter([1000.0, 1000.0 + account_status._ID_BIJ_EMAIL_TTL_SECONDEN + 1])
    with (
        patch("src.core.auth.account_status._zoek_id_bij_email", new=zoek),
        patch.object(account_status.time, "monotonic", side_effect=lambda: next(tijd)),
    ):
        await account_status.gebruikers_id_uit_sub("jan@x.test", 1)
        await account_status.gebruikers_id_uit_sub("jan@x.test", 1)

    assert zoek.await_count == 2


async def test_hetzelfde_e_mailadres_in_een_andere_tenant_wordt_apart_opgezocht(
    lege_id_cache: None,
) -> None:
    from src.core.auth.account_status import gebruikers_id_uit_sub

    zoek = AsyncMock(side_effect=[7, 9])
    with patch("src.core.auth.account_status._zoek_id_bij_email", new=zoek):
        een = await gebruikers_id_uit_sub("jan@x.test", 1)
        twee = await gebruikers_id_uit_sub("jan@x.test", 2)

    assert (een, twee) == ("u7", "u9")


# --------------------------------------------------------------------------- review 2026-10-27


def test_een_ipv4_adres_in_ipv6_vorm_van_een_proxy_telt_als_proxy() -> None:
    """`::ffff:172.18.0.2` is dezelfde proxy als `172.18.0.2`; anders deelt iedereen een emmer."""
    request = _request(client=("::ffff:172.18.0.2", 4000), xff=f"6.6.6.6, {ECHT_A}")

    assert governance_limiter._ip_key(request) == f"ip:{ECHT_A}"


def test_een_ipv4_adres_in_ipv6_vorm_heeft_dezelfde_emmer_als_de_gewone_vorm() -> None:
    gewoon = _request(client=("198.51.100.4", 4000))
    verpakt = _request(client=("::ffff:198.51.100.4", 4000))

    assert governance_limiter._ip_key(gewoon) == governance_limiter._ip_key(verpakt)


def test_een_verpakte_proxy_rechts_in_de_keten_wordt_overgeslagen() -> None:
    request = _request(client=PROXY, xff=f"{ECHT_A}, ::ffff:10.0.0.9")

    assert governance_limiter._ip_key(request) == f"ip:{ECHT_A}"


def test_een_verpakt_openbaar_adres_van_een_afzender_laat_xff_genegeerd() -> None:
    request = _request(client=("::ffff:198.51.100.4", 4000), xff="6.6.6.6")

    assert governance_limiter._ip_key(request) == "ip:198.51.100.4"


def test_twee_ipv6_adressen_in_hetzelfde_64_netwerk_delen_een_emmer() -> None:
    """Een client met een /64 kiest anders per verzoek een ander adres."""
    een = _request(client=("2001:db8:1:2::5", 4000))
    twee = _request(client=("2001:db8:1:2:aaaa:bbbb:cccc:dddd", 4000))

    assert governance_limiter._ip_key(een) == governance_limiter._ip_key(twee)


def test_ipv6_adressen_in_een_ander_64_netwerk_hebben_een_eigen_emmer() -> None:
    een = _request(client=("2001:db8:1:2::5", 4000))
    ander = _request(client=("2001:db8:1:3::5", 4000))

    assert governance_limiter._ip_key(een) != governance_limiter._ip_key(ander)


def test_een_ipv6_adres_uit_de_keten_telt_ook_per_64_netwerk() -> None:
    een = _request(client=PROXY, xff="6.6.6.6, 2001:db8:1:2::5")
    twee = _request(client=PROXY, xff="7.7.7.7, 2001:db8:1:2::9")

    assert governance_limiter._ip_key(een) == governance_limiter._ip_key(twee)


async def test_een_request_die_onwaar_is_telt_toch_als_request() -> None:
    """`Request` is een Mapping; met lengte 0 is hij onwaar (`MagicMock(spec=Request)` is dat ook).

    `if not request` nam zo'n object voor "geen request" aan; de vraag is `request is None`.
    """

    class LegeRequest(Request):
        def __len__(self) -> int:
            return 0

    onwaar = LegeRequest(scope={"type": "http", "headers": [], "client": ("198.51.100.8", 1)})
    assert not onwaar

    async def inhoud(request: Request) -> str:
        return "uitgevoerd"

    gedecoreerd = shared_limiter.privacy_rate_limit(max_requests=5, window_seconds=60)(inhoud)

    assert await gedecoreerd(request=onwaar) == "uitgevoerd"
