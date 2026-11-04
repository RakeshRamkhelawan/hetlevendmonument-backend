"""Overige punten uit het plan nazorg voor de SecurityMiddleware (2026-10-08).

1. Een fout in de middleware wordt gelogd via de logger, niet naar een tijdelijk bestand.
2. `/orchestrator` is niet meer PUBLIC: ingevoerd 2025-10-28 "for development", zonder ADR.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.core.security.security_manager import SecurityLevel
from src.core.security.security_middleware import SecurityMiddleware

TB_BESTAND = os.path.join(tempfile.gettempdir(), "security_middleware_traceback.log")


def _niveau(pad: str) -> SecurityLevel:
    middleware = SecurityMiddleware(MagicMock(), enable_security=True)
    verzoek = Request({"type": "http", "method": "GET", "path": pad, "headers": []})
    return middleware._determine_security_level(pad, verzoek)


@pytest.mark.unit
@pytest.mark.parametrize(
    "pad", ["/api/v1/orchestrator/status", "/api/v1/orchestrator/system-control", "/api/v1/agents/orchestrator"]
)
def test_orchestrator_paths_require_authentication(pad: str) -> None:
    assert _niveau(pad) == SecurityLevel.AUTHENTICATED


@pytest.mark.unit
def test_an_orchestrator_request_without_token_gets_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app = FastAPI()

    @app.get("/api/v1/orchestrator/status")
    async def status() -> dict[str, str]:
        return {"ok": "ja"}

    app.add_middleware(SecurityMiddleware, enable_security=True)
    assert TestClient(app).get("/api/v1/orchestrator/status").status_code == 401


@pytest.mark.unit
def test_a_middleware_error_is_logged_not_written_to_a_temp_file(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    if os.path.exists(TB_BESTAND):
        os.remove(TB_BESTAND)

    async def kapot(scope: object, receive: object, send: object) -> None:
        raise RuntimeError("boom")

    middleware = SecurityMiddleware(kapot, enable_security=True)  # type: ignore[arg-type]
    monkeypatch.setattr(middleware, "_determine_security_level", lambda *a: SecurityLevel.PUBLIC)
    response = TestClient(middleware).get("/x")  # type: ignore[arg-type]

    assert response.status_code == 500
    assert not os.path.exists(TB_BESTAND)
    assert "Security middleware error: RuntimeError: boom" in caplog.text
