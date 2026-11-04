import pytest
import subprocess
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.requests import Request

from src.core.middleware.audit_middleware import AuditLoggingMiddleware, RequestAuditLog

@pytest.mark.asyncio
async def test_request_audit_log_table_exists_in_schema(db_session: AsyncSession) -> None:
    """
    RED: faalt zolang er geen Alembic migratie bestaat die de tabel aanmaakt.
    GREEN: na aanmaken van de migratie en upgrade head.
    """
    table_exists = False
    try:
        await db_session.execute(text("SELECT 1 FROM request_audit_logs LIMIT 1"))
        table_exists = True
    except Exception:
        table_exists = False

    assert table_exists is True, (
        "request_audit_logs tabel ontbreekt -- voer alembic upgrade head uit"
    )

def test_audit_middleware_db_session_factory_not_none() -> None:
    """
    RED: de middleware is geconfigureerd met een factory.
    Dit is een configuratietest -- faalt zolang db_session_factory=None.
    """
    from src.core.api.setup.middleware_config import setup_middleware
    from fastapi import FastAPI

    app = FastAPI()
    setup_middleware(app)

    audit_mw = None
    for mw in app.user_middleware:
        if getattr(mw, "cls", None) is AuditLoggingMiddleware:
            audit_mw = mw
            break

    assert audit_mw is not None, "AuditLoggingMiddleware niet geregistreerd in app"
    assert audit_mw.kwargs.get("db_session_factory") is not None, (
        "db_session_factory mag niet None zijn -- wijs echte async session factory toe"
    )

@pytest.mark.asyncio
async def test_tenant_id_cast_to_string_before_db_write() -> None:
    """
    RED: faalt zolang tenant_id niet naar str() wordt gecast bij extractie.
    GREEN: na toevoegen van str(raw_tenant) cast in audit_middleware.py.
    """
    captured_entries = []

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    def fake_add(entry: Any) -> None:
        captured_entries.append(entry)

    mock_session.add = fake_add
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock(return_value=mock_session)

    # Simuleer authenticated user met integer tenant_id
    mock_user = MagicMock()
    mock_user.tenant_id = 42   # integer -- zoals JWT levert
    mock_user.id = 99

    async def homepage(request: Request) -> Response:
        request.state.user = mock_user
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(
        AuditLoggingMiddleware,
        log_to_db=True,
        db_session_factory=mock_factory,
    )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/")

    assert response.status_code == 200
    assert len(captured_entries) >= 1, "Geen audit entry aangemaakt"
    entry = captured_entries[0]
    assert isinstance(entry.tenant_id, str), (
        f"tenant_id moet str zijn, is {type(entry.tenant_id).__name__}"
    )
    assert entry.tenant_id == "42", (
        f"tenant_id moet '42' zijn, is {entry.tenant_id!r}"
    )

def test_alembic_heads_single_head_after_migration() -> None:
    """
    Draai na alembic upgrade head. Mag nooit 2 heads tonen.
    """
    result = subprocess.run(
        ["alembic", "-c", "src/alembic.ini", "heads"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    heads = [line for line in result.stdout.splitlines() if "(head)" in line]
    assert len(heads) == 1, (
        f"Verwacht 1 Alembic head, gevonden {len(heads)}: {result.stdout}"
    )

@pytest.mark.xfail(reason="Pre-existing index drift on workflow_executions outside scope of SP-WE-14b")
def test_alembic_no_drift_after_migration() -> None:
    """Alembic check mag geen drift melden na de migratie."""
    result = subprocess.run(
        ["alembic", "-c", "src/alembic.ini", "check"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    # Exit code 0 = geen drift
    assert result.returncode == 0, (
        f"Alembic drift gedetecteerd: {result.stdout}\n{result.stderr}"
    )
