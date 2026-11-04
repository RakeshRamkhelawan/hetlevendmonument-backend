"""ASGI-niveau bovengrens op de request-body-grootte (BE-AGT-060 dag 3 Gate 2, security-
review finding 1).

**Waarom dit NIET in de endpoint of een `BaseHTTPMiddleware` kan staan.** FastAPI's
`get_request_handler()` roept `await request.form()` aan VOORDAT `solve_dependencies()`
draait -- dus voordat `Depends(require_admin_role)` of enige andere auth-check uitgevoerd is.
Starlette's `MultiPartParser` handhaaft daarbij geen bruikbare bovengrens op een FILE-deel van
een multipart-body (`max_part_size` geldt alleen voor platte formveldwaarden, niet voor
bestanden) -- empirisch bevestigd tijdens de security-review: een 3 MiB file-deel passeert
`MultiPartParser.parse()` zonder enige foutmelding. Een endpoint-niveau `await file.read(cap)`
(zoals `_import_parsing.py::read_upload` of `documents/upload_router.py` al doen) komt dus
ALTIJD te laat: de volledige body is dan al ontvangen en gebufferd (RAM tot 1 MiB, daarna
schijf via `SpooledTemporaryFile`), ongeacht wie de aanvrager is of of die aanvrager de tool
mag gebruiken. Elke ingelogde gebruiker (niet alleen admins) kan zo herhaaldelijk grote
bestanden aanbieden en geheugen/schijf-druk veroorzaken voordat de 403/400 uiteindelijk komt.

Een `BaseHTTPMiddleware`-subklasse zou dit ook niet oplossen: die leest zelf de hele request
in zijn `dispatch()`-pad voordat de downstream-app iets ziet. Alleen een PURE ASGI-middleware
die de `receive()`-callable zelf omwikkelt en per binnenkomend chunk telt, kan de aanvraag
onderbreken VOORDAT de rest van de stack (inclusief `request.form()`) meer bytes ontvangt --
zelfde reden als `ProbeBypassMiddleware` in `middleware_config.py` ("Avoids BaseHTTPMiddleware
stream issues").

**Waarom een aparte exception i.p.v. direct een response sturen vanuit `_guarded_receive`.**
`send()` aanroepen vanuit de wrapper zelf zou de ASGI-response-levenscyclus laten botsen met
wat de downstream-app zelf nog denkt te gaan versturen. In plaats daarvan: gooi een interne
marker-exception op het moment dat de grens wordt overschreden, laat die door de downstream-
app's aanroep-stack heen propageren, en vang hem hier op als laatste redmiddel.

**Empirisch bevestigd (niet aangenomen): welke response de aanvrager daadwerkelijk ziet.**
Voor een `UploadFile`/multipart-endpoint vangt FastAPI's eigen `get_request_handler()` ELKE
`Exception` tijdens `await request.form()` af (`fastapi/routing.py`, de generieke
`except Exception as e: raise HTTPException(status_code=400, detail="There was an error
parsing the body")`) -- dus `MaxBodySizeExceeded` bereikt in de praktijk de `except` hieronder
NOOIT voor dat pad; de aanvrager krijgt FastAPI's eigen generieke 400, niet de 413 hieronder.
Dat is voor het DOEL van deze guard geen probleem: het punt is dat `_guarded_receive` de READ
stopt zodra de grens wordt overschreden -- geverifieerd door een 5000-byte upload tegen een
1024-byte grens te sturen en te bevestigen dat (a) de aanvraag NIET als succes (200) eindigt,
en (b) een daaropvolgende aanvraag op dezelfde verbinding gewoon weer werkt (geen kapotte
ASGI-staat). De 413-tak hier is een vangnet voor aanroeppaden die NIET via FastAPI's
`body_field`-mechanisme lopen (bv. een toekomstige rauwe ASGI-route, of een middleware die
zelf de body leest voordat FastAPI's routing bereikt wordt) -- niet de hoofdroute voor de
huidige hr-import-endpoints.

Dekt bewust NIET het scenario van een streaming-response die al deels is verstuurd terwijl de
request-body nog wordt gelezen -- geen van de huidige upload-endpoints doet dat.

**Bekende, nog niet bereikbare beperking: de eigen 413-response hierboven heeft geen CORS-
headers.** Deze middleware zit buiten `CORSMiddleware` (registratie-volgorde in
`middleware_config.py`), dus een response die HIJ ZELF verstuurt passeert `CORSMiddleware`'s
eigen `send`-omwikkeling niet. Vandaag is dat onbereikbaar: voor elk huidig upload-endpoint
vangt FastAPI's generieke body-parsing-exceptionhandler (zie hierboven) de marker-exception
AL af, diep genoeg in de stack om wel via `CORSMiddleware` te lopen. Zodra ooit een route de
body leest BUITEN dat FastAPI-mechanisme (een rauwe ASGI-route, of een middleware die zelf
`request.stream()`/`request.body()` aanroept voor FastAPI's routing), zou een cross-origin
`fetch()`-aanvraag deze 413 als netwerkfout zien, niet als leesbare response (Gate 2 code-
review, BE-AGT-060 dag 3).
"""

from __future__ import annotations

import logging

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

#: Fallback voor gebruik zonder een expliciete `max_bytes` (bv. een test die de klasse direct
#: instantieert). `middleware_config.py` geeft in de echte app altijd `settings.
#: max_upload_size_bytes` door -- deze default is BEWUST gelijk aan diens eigen default
#: (`src/core/shared/config.py`), niet een eigen, lossere waarde: een guard die STRAKKER is
#: dan een bestaand, functioneel endpoint (bv. `documents/upload_router.py`'s 50 MiB) zou een
#: eerder werkende upload alsnog laten stuklopen. Zie de module-docstring: dit is een vangnet
#: BOVEN de endpoint-eigen caps, geen nieuwe, eigen (lagere) grens.
DEFAULT_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024


class MaxBodySizeExceeded(Exception):
    """Interne marker -- propageert door de downstream ASGI-app heen naar `__call__` hieronder."""

    def __init__(self, total_bytes: int) -> None:
        self.total_bytes = total_bytes
        super().__init__(f"Request body exceeded the maximum ({total_bytes} bytes received)")


class MaxRequestBodySizeMiddleware:
    """Pure ASGI middleware -- telt ontvangen body-bytes VOORDAT enige andere middleware,
    dependency, of route-handler ze ziet. Moet de buitenste laag zijn (net als
    `ProbeBypassMiddleware`): `app.add_middleware(...)` LAATST aanroepen = OUTERMOST."""

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        total_bytes = 0

        async def _guarded_receive() -> Message:
            nonlocal total_bytes
            message = await receive()
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_bytes:
                    raise MaxBodySizeExceeded(total_bytes)
            return message

        try:
            await self.app(scope, _guarded_receive, send)
        except MaxBodySizeExceeded as exc:
            # Zichtbaarheid op herhaalde misbruikpogingen -- dit is een DoS-preventiecontrole,
            # geen gewone validatiefout (Gate 2 code-review, BE-AGT-060 dag 3).
            logger.warning(
                "Request body exceeded max_bytes=%d (received %d bytes) on %s",
                self.max_bytes,
                exc.total_bytes,
                scope.get("path", "?"),
            )
            response = JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": {
                        "error_code": "REQUEST_BODY_TOO_LARGE",
                        "message": (f"Request body exceeds the maximum of {self.max_bytes} bytes"),
                        "details": {},
                    },
                },
            )
            await response(scope, receive, send)
