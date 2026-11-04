import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Response

from src.core.api.v1.copilot_intent.parse_router import (
    router,
    parse_intent,
    IntentRequest,
    IntentParseResponse,
    AgentTypeEnum,
)
from src.core.models.rbac_models import User


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/v1/intents/parse" in paths


@pytest.mark.asyncio
async def test_parse_intent_success() -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.tenant_id = 42

    req = IntentRequest(query="create a new workflow for invoice processing")
    resp_obj = Response()

    resp = await parse_intent(
        request=req,
        response=resp_obj,
        current_user=user,
        db=AsyncMock(),
    )

    assert isinstance(resp, IntentParseResponse)
    assert resp.success is True
    assert resp.intent is not None
    assert resp.intent.recommended_agent == AgentTypeEnum.WORKFLOW
    assert resp.intent.confidence >= 0.5
    assert "Deprecation" in resp_obj.headers
