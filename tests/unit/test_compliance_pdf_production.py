"""Production-level tests for compliance PDF export.

Covers drift-fixes, UTF-8 safety, AuditLog writes, i18n, and metrics.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.execute = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_calculator_with_result_obj():
    """Return a ComplianceScoreResult-like object, not a float."""
    calc = AsyncMock()
    score_result = SimpleNamespace(
        overall_score=0.82,
        per_policy={"gdpr": 0.9, "ai_act": 0.74},
        evaluated_at="2026-05-15T10:00:00Z",
    )
    calc.calculate_overall_score = AsyncMock(return_value=score_result)
    return calc


@pytest_asyncio.fixture
async def pdf_client(mock_calculator_with_result_obj, mock_db_session):
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_current_user():
        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    with patch(
        "src.core.api.v1.compliance.router.ComplianceScoreCalculator",
        return_value=mock_calculator_with_result_obj,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_endpoint_extracts_overall_score_from_result_object(pdf_client):
    """Drift-fix: ComplianceScoreCalculator returns object, not float."""
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200, (
        "Endpoint must return 200 even though the mock returns an object instead of float. "
        "If 500: the endpoint still multiplies an object by 100 (AttributeError)."
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_endpoint_uses_loguru_style_logging(pdf_client, caplog):
    """Drift-fix: no `extra={...}` kwarg in loguru calls."""
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    # Loguru bind() pattern: tenant_id appears in records[].extra, not as raw extra= dict
    # This test passes as long as no TypeError occurs from `extra=` on a loguru call


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_endpoint_generates_valid_pdf(pdf_client):
    """DejaVuSans must produce valid PDF bytes without crashing."""
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200, (
        f"Expected 200 with DejaVuSans. Got {response.status_code}. Body: {response.content[:200]}"
    )
    assert response.content[:4] == b"%PDF", "PDF magic bytes missing"


@pytest.mark.unit
def test_pdf_loaded_dejavu_font_not_helvetica():
    """Verify that code loads DejaVu, not Helvetica.

    After ADR-033 Strangler Fig, PDF logic is in pdf_router.py (Laag 1).
    """
    import inspect

    import src.core.api.v1.compliance.pdf_router as pdf_router_module

    source = inspect.getsource(pdf_router_module)
    assert "DejaVu" in source, "DejaVuSans must be loaded as font"
    assert 'set_font("Helvetica"' not in source, (
        "Helvetica is a Latin-1 core-font and crashes on non-Western characters. "
        "Use DejaVu after add_font(uni=True)."
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_export_writes_audit_log_row(pdf_client, mock_db_session):
    """Production requirement: every export produces an AuditLog row."""
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200

    # Verify that db.add was called with an AuditLog instance
    mock_db_session.add.assert_called()
    added_obj = mock_db_session.add.call_args[0][0]

    # Verify all NOT NULL columns
    assert added_obj.tenant_id == 1
    assert added_obj.user_id == 1
    assert added_obj.action == "compliance_pdf_export"
    assert added_obj.resource == "compliance_report"
    assert added_obj.timestamp is not None
    assert added_obj.event_type is not None  # NOT NULL
    assert added_obj.threat_level is not None  # NOT NULL, use "INFO" for read-actions
    assert added_obj.client_ip is not None  # NOT NULL, use request.client.host
    assert added_obj.endpoint == "/api/v1/compliance/report/pdf"
    assert added_obj.description  # NOT NULL, not empty
    assert added_obj.event_metadata is not None  # JSON dict


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_export_audit_log_failure_does_not_break_response(pdf_client, mock_db_session):
    """best_effort: audit failure must not block the PDF response."""
    # Simulate DB error on the audit write
    mock_db_session.commit.side_effect = Exception("audit DB unreachable")

    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )

    # PDF must still be delivered
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


@pytest.mark.asyncio
@pytest.mark.security
@pytest.mark.multi_tenant
async def test_audit_log_uses_jwt_tenant_id_not_request_param(pdf_client, mock_db_session):
    """Tenant binding: AuditLog.tenant_id comes EXCLUSIVELY from JWT, not query/body."""
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf?tenant_id=999",  # spoofing attempt
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    added_obj = mock_db_session.add.call_args[0][0]
    assert added_obj.tenant_id == 1, (
        f"tenant_id must come from JWT (1), not from query (999). Got: {added_obj.tenant_id}"
    )


import re


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_has_metadata(pdf_client):
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    pdf_bytes = response.content

    # PDF metadata sits in /Info dict — simple regex check
    assert b"/Title" in pdf_bytes
    assert b"AI Act Compliance" in pdf_bytes
    assert b"/Author" in pdf_bytes
    assert b"/Creator" in pdf_bytes


@pytest_asyncio.fixture
async def pdf_client_with_policies(mock_db_session):
    """Mock with per_policy data."""
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_user():
        return SimpleNamespace(
            id=1, sub="1", user_id=1, tenant_id=1, email="test@example.com", roles=["user"]
        )

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    calc = AsyncMock()
    calc.calculate_overall_score = AsyncMock(
        return_value=SimpleNamespace(
            overall_score=0.82,
            per_policy={
                "gdpr": 0.9,
                "ai_act": 0.74,
                "internal_data_classification": 0.85,
            },
        )
    )
    with patch(
        "src.core.api.v1.compliance.router.ComplianceScoreCalculator",
        return_value=calc,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_has_multiple_pages(pdf_client_with_policies):
    """With per_policy data there must be at least a cover page + per-policy page."""
    response = await pdf_client_with_policies.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    pdf_bytes = response.content

    # Count /Page entries (excl. /Pages container)
    page_count = len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes))
    assert page_count >= 2, f"Expected >= 2 pages, got {page_count}"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_returns_english_when_accept_language_en(pdf_client):
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={
            "Authorization": "Bearer test-token",
            "Accept-Language": "en",
        },
    )
    assert response.status_code == 200
    pdf_bytes = response.content
    # PDF metadata title is stored as plain text (not compressed)
    assert b"/Title (AI Act Compliance Report" in pdf_bytes


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_returns_dutch_when_accept_language_nl_or_missing(pdf_client):
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={
            "Authorization": "Bearer test-token",
            "Accept-Language": "nl",
        },
    )
    assert response.status_code == 200
    pdf_bytes = response.content
    # PDF metadata title is stored as plain text (not compressed)
    assert b"/Title (AI Act Compliance Rapport" in pdf_bytes


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_export_increments_prometheus_counter(pdf_client):
    from src.core.observability.compliance_metrics import compliance_pdf_exports_total

    before = compliance_pdf_exports_total.labels(
        tenant_id="1", language="nl", status="success"
    )._value.get()

    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200

    after = compliance_pdf_exports_total.labels(
        tenant_id="1", language="nl", status="success"
    )._value.get()

    assert after == before + 1, f"Counter moet +1 zijn, before={before} after={after}"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_export_creates_otel_span(pdf_client):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # tests/fixtures/api.py sets OTEL_SDK_DISABLED=true globally;
    # explicitly re-enable so spans are recorded.
    provider._disabled = False
    test_tracer = provider.get_tracer("test")

    with patch(
        "src.core.api.v1.compliance.pdf_router.trace.get_tracer",
        return_value=test_tracer,
    ):
        response = await pdf_client.get(
            "/api/v1/compliance/report/pdf",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200

    spans = exporter.get_finished_spans()
    pdf_spans = [s for s in spans if s.name == "compliance.pdf_export"]
    assert len(pdf_spans) >= 1, (
        f"Verwacht span 'compliance.pdf_export', kreeg: {[s.name for s in spans]}"
    )

    attrs = pdf_spans[0].attributes
    assert attrs.get("tenant_id") == 1
    assert attrs.get("language") in ("nl", "en")
