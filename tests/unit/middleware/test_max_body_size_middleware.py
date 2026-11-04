"""`MaxRequestBodySizeMiddleware` (BE-AGT-060 dag 3 Gate 2, security-review finding 1).

Twee lagen tests: een lage-niveau ASGI-test die de byte-tellogica direct aanroept (precies,
geen FastAPI-overhead), en een TestClient-integratietest die bewijst dat de guard ook
daadwerkelijk werkt achter een echte multipart file-upload-route -- exact het scenario van de
hr-import-endpoints.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient
from starlette.types import Message, Scope

from src.core.middleware.max_body_size_middleware import MaxRequestBodySizeMiddleware

pytestmark = pytest.mark.unit


def _make_receive(chunks: list[bytes]) -> Any:
    """Levert de opgegeven chunks als opeenvolgende `http.request`-ASGI-berichten."""
    remaining = list(chunks)

    async def _receive() -> Message:
        if remaining:
            body = remaining.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(remaining)}
        return {"type": "http.request", "body": b"", "more_body": False}

    return _receive


async def _drain(
    app: Any, scope: Scope, receive: Any
) -> tuple[list[Message], BaseException | None]:
    sent: list[Message] = []

    async def _send(message: Message) -> None:
        sent.append(message)

    try:
        await app(scope, receive, _send)
        return sent, None
    except BaseException as exc:  # noqa: BLE001 -- de test wil de exception zelf inspecteren
        return sent, exc


class TestLowLevelByteCounting:
    async def test_chunks_under_the_cap_reach_the_downstream_app_unmodified(self) -> None:
        received_bodies: list[bytes] = []

        async def _downstream_app(scope: Scope, receive: Any, send: Any) -> None:
            while True:
                message = await receive()
                received_bodies.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = MaxRequestBodySizeMiddleware(_downstream_app, max_bytes=1024)
        receive = _make_receive([b"x" * 100])
        sent, exc = await _drain(middleware, {"type": "http"}, receive)

        assert exc is None
        assert received_bodies == [b"x" * 100]
        assert sent[0]["status"] == 200

    async def test_a_chunk_that_pushes_the_total_over_the_cap_raises_before_the_next_chunk(
        self,
    ) -> None:
        """Met `max_bytes=150` en chunks van 100 bytes duwt de TWEEDE chunk de teller over de
        grens (100+100=200>150) -- de downstream-app mag hem NOOIT zien; alleen de eerste
        chunk mag ontvangen zijn. (Eerder stond hier "de derde chunk": empirisch onjuist,
        gevonden door Gate 2 code-review mutatietest, BE-AGT-060 dag 3.)

        Hier gebruikt de downstream-app een kale lus zonder eigen `except` -- de middleware
        vangt zijn eigen `MaxBodySizeExceeded` dus altijd zelf op (bevestigd: `exc is None`
        hieronder, geen `isinstance`-slag meer nodig -- die tak was dood: `_drain` kan de
        marker-exception nooit zien omdat `__call__` hem al opvangt voor hij daar komt)."""
        received_bodies: list[bytes] = []

        async def _downstream_app(scope: Scope, receive: Any, send: Any) -> None:
            while True:
                message = await receive()
                received_bodies.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break

        middleware = MaxRequestBodySizeMiddleware(_downstream_app, max_bytes=150)
        receive = _make_receive([b"a" * 100, b"b" * 100, b"c" * 100])
        sent, exc = await _drain(middleware, {"type": "http"}, receive)

        assert exc is None
        assert received_bodies == [b"a" * 100]  # de tweede chunk (b"b"*100) is NOOIT ontvangen
        # De middleware's EIGEN 413-vangnet moet ook echt de juiste vorm sturen -- zonder deze
        # assertie bleven alle 6 tests in dit bestand groen toen `status_code`/`error_code`
        # naar onzin-waarden gemuteerd werden (Gate 2 code-review mutatietest).
        start_message = next(m for m in sent if m["type"] == "http.response.start")
        assert start_message["status"] == 413
        body_message = next(m for m in sent if m["type"] == "http.response.body")
        body = json.loads(body_message["body"])
        assert body["error"]["error_code"] == "REQUEST_BODY_TOO_LARGE"

    async def test_exactly_max_bytes_is_accepted_one_byte_more_is_rejected(self) -> None:
        """Grensgeval: `>` niet `>=` -- een upload van precies `max_bytes` mag NOOIT worden
        afgewezen (geen test dekte dit eerder, Gate 2 code-review)."""

        async def _accepting_downstream_app(scope: Scope, receive: Any, send: Any) -> None:
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        exactly_at_cap = MaxRequestBodySizeMiddleware(_accepting_downstream_app, max_bytes=100)
        sent, exc = await _drain(exactly_at_cap, {"type": "http"}, _make_receive([b"x" * 100]))
        assert exc is None
        assert sent[0]["status"] == 200

        one_over_cap = MaxRequestBodySizeMiddleware(_accepting_downstream_app, max_bytes=100)
        sent, exc = await _drain(one_over_cap, {"type": "http"}, _make_receive([b"x" * 101]))
        assert exc is None  # de middleware vangt MaxBodySizeExceeded zelf op
        assert sent[0]["status"] == 413


class TestNonHttpScopePassesThrough:
    async def test_a_lifespan_scope_is_never_wrapped(self) -> None:
        """Bewijst dat `receive` ONGEWIJZIGD doorgegeven wordt voor een non-http scope --
        niet alleen dat `scope` ongewijzigd is. Een test die alleen `scope` controleert zou
        identiek slagen als `receive` per ongeluk ALTIJD gewrapt werd (security-review
        BE-AGT-060 dag 3, finding: de test beloofde meer dan hij toetste)."""
        received_objects: list[Any] = []

        async def _downstream_app(scope: Scope, receive: Any, send: Any) -> None:
            received_objects.append(receive)
            await receive()

        original_receive = _make_receive([])
        middleware = MaxRequestBodySizeMiddleware(_downstream_app, max_bytes=10)
        await middleware({"type": "lifespan"}, original_receive, lambda m: None)

        assert received_objects == [original_receive]  # exact hetzelfde object, geen wrapper


class TestRealUploadEndpoint:
    @pytest.fixture
    def app(self) -> FastAPI:
        application = FastAPI()
        application.add_middleware(MaxRequestBodySizeMiddleware, max_bytes=1024)

        @application.post("/upload")
        async def upload(file: UploadFile = File(...)) -> dict[str, int]:
            content = await file.read()
            return {"received": len(content)}

        return application

    def test_a_file_under_the_cap_uploads_successfully(self, app: FastAPI) -> None:
        client = TestClient(app)

        response = client.post(
            "/upload", files={"file": ("a.txt", BytesIO(b"x" * 100), "text/plain")}
        )

        assert response.status_code == 200
        assert response.json() == {"received": 100}

    def test_a_file_over_the_cap_is_rejected_not_silently_accepted(self, app: FastAPI) -> None:
        client = TestClient(app)

        response = client.post(
            "/upload", files={"file": ("b.txt", BytesIO(b"x" * 5000), "text/plain")}
        )

        assert response.status_code != 200

    def test_the_connection_still_works_normally_after_a_rejected_upload(
        self, app: FastAPI
    ) -> None:
        """Bewijst dat het afwijzen van een te grote upload de ASGI-verbindingsstaat niet
        corrumpeert -- een volgende, geldige aanvraag moet gewoon slagen. De EERSTE aanvraag
        moet ook daadwerkelijk zijn afgewezen -- zonder die assertie bewijst deze test niets
        over een afwijzing (Gate 2 code-review mutatietest, BE-AGT-060 dag 3: de size-check
        volledig uitgeschakeld liet deze test toch groen blijven)."""
        client = TestClient(app)
        first_response = client.post(
            "/upload", files={"file": ("b.txt", BytesIO(b"x" * 5000), "text/plain")}
        )
        assert first_response.status_code != 200

        response = client.post(
            "/upload", files={"file": ("c.txt", BytesIO(b"y" * 50), "text/plain")}
        )

        assert response.status_code == 200
        assert response.json() == {"received": 50}
