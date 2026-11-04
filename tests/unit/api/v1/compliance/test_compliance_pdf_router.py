import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.core.api.v1.compliance.pdf_router import pdf_router, download_compliance_report
from src.core.models.rbac_models import User
from tests.helpers.limiet_request import echte_request


def test_routes_registered() -> None:
    paths = [r.path for r in pdf_router.routes]
    assert "/report/pdf" in paths


@pytest.mark.asyncio
async def test_download_compliance_report_success() -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.tenant_id = 42

    calculator = AsyncMock()
    mock_score = MagicMock()
    mock_score.overall_score = 0.95
    mock_score.per_policy = {"audit_logging": 0.9}
    calculator.calculate_overall_score.return_value = mock_score

    agg_svc = AsyncMock()
    agg_svc.get_ai_decisions.return_value = []
    agg_svc.db_session = AsyncMock()

    req = echte_request(headers={"accept-language": "nl"}, client_host="127.0.0.1")

    with patch("src.core.api.v1.compliance.pdf_router.AuditService.log_action", new_callable=AsyncMock):
        resp = await download_compliance_report(
            request=req,
            current_user=user,
            calculator=calculator,
            agg_svc=agg_svc,
        )

        assert isinstance(resp, StreamingResponse)
        assert resp.media_type == "application/pdf"
        assert "attachment; filename=" in resp.headers["Content-Disposition"]
