"""Een publiek endpoint mag niet stuklopen op een oud of kapot tokencookie.

**De bevinding.** `TenantMiddleware` laat een publiek endpoint ZONDER token al anoniem door
(`tenant_middleware.py`, de tak `if is_public and not token`). Maar zodra er WEL een token
meekomt valt het verzoek door naar de token-validatie, en elk faalpad daar geeft 401 -- ook voor
een publiek endpoint.

Waarom dat een echt probleem is en geen theorie: een browser stuurt cookies ALTIJD mee. Wie een
verlopen `access_token`-cookie heeft en daarna naar `/api/v1/auth/login` of `/api/v1/auth/refresh`
gaat, krijgt 401 uit de middleware voordat de route-handler ook maar draait. Precies de drie
endpoints die je nodig hebt om uit die toestand te komen, zijn dan onbereikbaar. Gemeld door de
Copilot-review op PR #162.

**Wat de fix moet doen.** Bij een publiek endpoint gedraagt een kapot token zich als GEEN token:
anoniem doorlaten en de handler laten beslissen. Er wordt daarmee geen enkel privilege toegekend
-- er komt juist geen tenantcontext -- en dat is exact wat de bestaande tokenloze tak al doet.

**Wat de fix NIET mag aantasten, en dat staat hier als tegenrichting in dit bestand:** de
OP-62-bescherming. Een NIET-publiek endpoint moet 401 blijven geven, met of zonder token. Zonder
die helft zou "laat alles door" een geldige implementatie zijn.

De vier faalpaden in de middleware, elk met een eigen test hieronder:
1. `verify_token` geeft None terug (verlopen of ongeldige handtekening);
2. het token mist de `tenant_id`-claim (buiten single_tenant-modus);
3. de `tenant_id` is een string die geen getal is;
4. er treedt een onverwachte fout op tijdens de verificatie (het vangnet-`except`).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.middleware.tenant_middleware import TenantMiddleware

#: Staat in `PublicEndpointRegistry.PUBLIC_PATHS`. Juist dit endpoint heb je nodig om uit een
#: verlopen sessie te komen, dus juist hier doet de 401 de meeste schade.
PUBLIEK_PAD = "/api/v1/auth/refresh"
NIET_PUBLIEK_PAD = "/api/v1/agents"

#: Wat een browser meestuurt als er ooit is ingelogd. De waarde is bewust onzin: het gaat erom
#: dat er IETS staat, want dat is wat het verzoek door de tokenloze tak heen duwt.
VEROUDERD_COOKIE = [(b"cookie", b"access_token=verlopen.rommel.token")]


@pytest.fixture
def mock_app():
    """Een minimale ASGI-app die 200 teruggeeft, zodat 'doorgelaten' zichtbaar is."""

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def _scope(pad: str, headers: list[tuple[bytes, bytes]]) -> dict:
    return {
        "type": "http",
        "path": pad,
        "method": "POST",
        "headers": headers,
        "client": ("127.0.0.1", 8000),
    }


async def _status(middleware: TenantMiddleware, scope: dict) -> int:
    antwoorden: list[dict] = []

    async def send(message):
        antwoorden.append(message)

    await middleware(scope, AsyncMock(), send)
    return antwoorden[0]["status"]


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_public_endpoint_passes_through_with_an_expired_token(mock_jwt, mock_app):
    """Faalpad 1: `verify_token` geeft None -- verlopen of ongeldige handtekening."""
    mock_jwt.verify_token.return_value = None

    status = await _status(TenantMiddleware(mock_app), _scope(PUBLIEK_PAD, VEROUDERD_COOKIE))

    assert status == 200, (
        f"Publiek endpoint {PUBLIEK_PAD} gaf {status} op een verlopen cookie. Een browser stuurt "
        "dat cookie altijd mee, dus dit maakt juist de endpoints onbereikbaar waarmee je een "
        "verlopen sessie zou herstellen."
    )


@pytest.mark.asyncio
@patch("src.core.middleware.tenant_middleware.DEPLOYMENT_MODE", "saas")
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_public_endpoint_passes_through_without_a_tenant_claim(mock_jwt, mock_app):
    """Faalpad 2: het token verifieert, maar mist de `tenant_id`-claim.

    Dit is het scenario van een token van voor de tenant-claim werd toegevoegd. `saas` is hier
    expliciet gezet, want in `single_tenant` valt de code al terug op tenant_id=1.
    """
    mock_jwt.verify_token.return_value = {"sub": "gebruiker-1"}

    status = await _status(TenantMiddleware(mock_app), _scope(PUBLIEK_PAD, VEROUDERD_COOKIE))

    assert status == 200, (
        f"Publiek endpoint {PUBLIEK_PAD} gaf {status} op een token zonder tenant-claim. Een "
        "publiek endpoint heeft geen tenantcontext nodig -- de tokenloze tak laat immers ook door."
    )


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_public_endpoint_passes_through_with_an_unparseable_tenant(mock_jwt, mock_app):
    """Faalpad 3: de `tenant_id` is een string die geen getal is."""
    mock_jwt.verify_token.return_value = {"sub": "gebruiker-1", "tenant_id": "geen-getal"}

    status = await _status(TenantMiddleware(mock_app), _scope(PUBLIEK_PAD, VEROUDERD_COOKIE))

    assert status == 200, (
        f"Publiek endpoint {PUBLIEK_PAD} gaf {status} op een onbruikbare tenant_id."
    )


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_public_endpoint_passes_through_when_verification_raises(mock_jwt, mock_app):
    """Faalpad 4: het vangnet-`except`, als de verificatie zelf ontploft."""
    mock_jwt.verify_token.side_effect = RuntimeError("jwt-bibliotheek struikelt")

    status = await _status(TenantMiddleware(mock_app), _scope(PUBLIEK_PAD, VEROUDERD_COOKIE))

    assert status == 200, (
        f"Publiek endpoint {PUBLIEK_PAD} gaf {status} toen de tokenverificatie een fout gooide."
    )


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_the_downstream_app_is_called_exactly_once(mock_jwt):
    """De doorlaat mag de handler NIET twee keer draaien.

    Gemeten door een Gate 2-reviewer op de eerste versie van deze fix: die riep `self.app` aan
    VANUIT de `try` met het vangnet-`except`. Een fout in de route-handler werd daardoor door dat
    vangnet opgevangen, waarna de handler een TWEEDE keer draaide en er twee volledige
    HTTP-antwoorden werden verstuurd. Op een POST naar `/api/v1/auth/register` betekent dat een
    dubbele registratie en een dubbele magic-link-mail.

    Deze test faalt op die versie en slaagt zodra de doorlaat buiten de try gebeurt.
    """
    mock_jwt.verify_token.return_value = None
    aanroepen = []

    async def tellende_app(scope, receive, send):
        aanroepen.append(scope["path"])
        raise RuntimeError("de route-handler ontploft")

    middleware = TenantMiddleware(tellende_app)
    with pytest.raises(RuntimeError):
        await middleware(_scope(PUBLIEK_PAD, VEROUDERD_COOKIE), AsyncMock(), AsyncMock())

    assert len(aanroepen) == 1, (
        f"De route-handler is {len(aanroepen)} keer aangeroepen. Bij een POST betekent elke "
        "extra aanroep een dubbele bijwerking -- een tweede registratie, een tweede e-mail."
    )


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_an_anonymous_pass_through_carries_no_tenant_context(mock_jwt):
    """De doorlaat mag GEEN tenantcontext meegeven -- ook niet half.

    Zonder deze assertie zou een implementatie die bij de doorlaat `tenant_id=1` en
    `roles=["admin"]` zet alle andere tests groen houden. Een reviewer heeft precies die
    variant geschreven en gemeten dat hij groen bleef. De commit-boodschap beweerde in proza dat
    er geen privilege wordt toegekend; hier staat het als toets.

    Het scenario is het vangnet-pad, want daar is de kans op achtergebleven context het grootst:
    de fout treedt op NA `set_tenant_id`.
    """
    from src.core.middleware.tenant_context import _current_user_scopes, get_tenant_id

    mock_jwt.verify_token.side_effect = RuntimeError("na het zetten van de context")
    gezien: dict = {}

    async def spiedende_app(scope, receive, send):
        gezien["state"] = dict(scope.get("state", {}))
        gezien["tenant"] = get_tenant_id()
        gezien["scopes"] = _current_user_scopes.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    await TenantMiddleware(spiedende_app)(
        _scope(PUBLIEK_PAD, VEROUDERD_COOKIE), AsyncMock(), AsyncMock()
    )

    achtergebleven = {
        sleutel: gezien["state"].get(sleutel)
        for sleutel in ("tenant_id", "user_id", "email", "roles", "scopes")
        if gezien["state"].get(sleutel) is not None
    }
    assert not achtergebleven and not gezien["tenant"] and not gezien["scopes"], (
        f"De anonieme doorlaat gaf toch context mee: state={achtergebleven}, "
        f"tenant={gezien['tenant']}, scopes={gezien['scopes']}."
    )


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_public_endpoint_with_a_valid_token_still_gets_tenant_context(mock_jwt):
    """TEGENRICHTING: een GELDIG token op een publiek pad hoort wel context te krijgen.

    Zonder deze helft zou "publiek endpoint krijgt nooit context" een geldige implementatie zijn
    -- een reviewer heeft ook die variant geschreven en gemeten dat hij groen bleef. Publieke
    endpoints die optioneel een ingelogde gebruiker herkennen, zouden dan stil anoniem worden.
    """
    from src.core.middleware.tenant_context import get_tenant_id

    mock_jwt.verify_token.return_value = {"sub": "gebruiker-1", "tenant_id": 42}
    gezien: dict = {}

    async def spiedende_app(scope, receive, send):
        gezien["tenant"] = get_tenant_id()
        gezien["state"] = dict(scope.get("state", {}))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    await TenantMiddleware(spiedende_app)(
        _scope(PUBLIEK_PAD, [(b"cookie", b"access_token=geldig")]), AsyncMock(), AsyncMock()
    )

    assert gezien["tenant"] == 42 and gezien["state"].get("tenant_id") == 42, (
        f"Een geldig token op een publiek pad leverde geen tenantcontext op: "
        f"tenant={gezien.get('tenant')}, state={gezien.get('state')}."
    )


@pytest.mark.asyncio
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_protected_endpoint_still_rejects_an_expired_token(mock_jwt, mock_app):
    """TEGENRICHTING: op een NIET-publiek pad blijft een kapot token gewoon 401.

    Zonder deze helft zou "laat alles door" een geldige implementatie van de fix zijn.
    """
    mock_jwt.verify_token.return_value = None

    status = await _status(TenantMiddleware(mock_app), _scope(NIET_PUBLIEK_PAD, VEROUDERD_COOKIE))

    assert status == 401, (
        f"Beschermd endpoint {NIET_PUBLIEK_PAD} gaf {status} op een verlopen token. De fix voor "
        "publieke endpoints mag de authenticatie op beschermde paden niet aanraken."
    )


@pytest.mark.asyncio
async def test_a_protected_endpoint_still_rejects_a_request_without_a_token(mock_app):
    """TEGENRICHTING: de OP-62-bescherming blijft overeind.

    Een verzoek zonder token kreeg ooit in single_tenant-modus adminrechten zonder verificatie.
    Die tak mag door deze wijziging niet verschuiven.
    """
    status = await _status(TenantMiddleware(mock_app), _scope(NIET_PUBLIEK_PAD, []))

    assert status == 401, (
        f"Beschermd endpoint {NIET_PUBLIEK_PAD} gaf {status} zonder token -- de OP-62-omzeiling "
        "is terug."
    )


@pytest.mark.asyncio
@patch("src.core.middleware.tenant_middleware.DEPLOYMENT_MODE", "saas")
@patch("src.core.middleware.tenant_middleware.log_security_event")
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_a_pass_through_still_emits_the_security_event(mock_jwt, mock_event, mock_app):
    """Doorlaten en AUDITEN sluiten elkaar niet uit.

    Een Gate 2-reviewer mat dat de eerste versie van deze fix het aantal
    `TENANT_CONTEXT_FAILED`-events op een publiek pad van 1 naar 0 bracht: de guard stond boven
    de `else` die dat event afvuurde. Dat is een detectiedegradatie op precies de endpoints die
    een aanvaller het eerst probeert -- een GELDIG ondertekend token met een kapotte claimset is
    het signaal van sleutelcompromittering of tokenvervalsing.
    """
    mock_jwt.verify_token.return_value = {"sub": "gebruiker-1"}
    mock_event.return_value = None

    status = await _status(TenantMiddleware(mock_app), _scope(PUBLIEK_PAD, VEROUDERD_COOKIE))

    assert status == 200 and mock_event.await_count == 1, (
        f"status={status}, security-events={mock_event.await_count}. Het verzoek hoort door te "
        "gaan EN geauditeerd te worden; nul events betekent dat deze detectie stil is verdwenen."
    )


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over tenantcontext en tokens, niet over de accountstatus, en hebben geen database.

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
