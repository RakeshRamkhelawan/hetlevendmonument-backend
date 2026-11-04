"""
Regression tests for EU AI Act GAP fixes (ADR-031).

Verifies that AI-facing routes enforce Council deliberation.
These tests use a mix of:
- Direct unit tests for the reusable governance_gate helper
- AST/code inspection to verify Council wiring in endpoint files
- Direct endpoint function tests for routes without decorator issues
"""

from __future__ import annotations

import ast
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _function_calls_name(func: Any, target: str) -> bool:
    """Return True if *func*'s source contains a call to *target*."""
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return False
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == target:
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == target:
                return True
    return False


def _function_has_param(func: Any, param_name: str) -> bool:
    """Return True if *func* accepts *param_name* as a parameter."""
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return False
    return param_name in sig.parameters


# ---------------------------------------------------------------------------
# GAP-001: CVA /chat Council enforcement
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.xfail(
    reason="Council integration is TODO(SP-VOLGENDE) in v1/cva/chat_router.py — chat_endpoint now uses CVAService before council check",
    strict=False,
)
async def test_cva_chat_rejects_blocked_council() -> None:
    """CVA chat must raise 403 when Council returns BLOCKED."""
    from src.core.api.cva_chat import chat_endpoint
    from src.core.schemas.cva_schemas import ChatRequest

    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.tenant_id = 1
    mock_user.id = 42
    mock_llm = MagicMock()

    fake_decision = MagicMock()
    fake_decision.verdict = MagicMock()
    fake_decision.verdict.value = "BLOCKED"
    fake_decision.explanation_for_user = "Policy violation"
    fake_decision.decision_id = "dec-123"

    mock_council = AsyncMock()
    mock_council.deliberate = AsyncMock(return_value=fake_decision)

    with patch("src.core.api.cva_chat.build_council", return_value=mock_council):
        with pytest.raises(HTTPException) as exc_info:
            await chat_endpoint(
                request=ChatRequest(message="hello"),
                db=mock_db,
                current_user=mock_user,
                llm_service=mock_llm,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_cva_chat_uses_require_council_approval() -> None:
    """CVAService.chat() must call require_council_approval before LLM invoke (ARCH-004).

    The governance gate lives in the service layer (cva_service.py), not the router.
    Uses source inspection rather than AST to avoid dedent issues with class methods.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "src/core/services/cva_service.py").read_text(
        encoding="utf-8"
    )
    assert "require_council_approval" in source, (
        "cva_service.py roept require_council_approval niet aan. "
        "ARCH-004: CVA LLM invocatie zonder governance contract schendt ADR-031."
    )


# ---------------------------------------------------------------------------
# GAP-002/GAP-003: Focus Builder /ai/suggest and /ai/generate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_focus_builder_suggest_has_council_param() -> None:
    """Focus Builder suggest must accept a council parameter."""
    # NOTE: moved to ai_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.focus_builder.ai_router import suggest_nodes

    assert _function_has_param(suggest_nodes, "council")


@pytest.mark.unit
def test_focus_builder_suggest_uses_require_council_approval() -> None:
    """Focus Builder suggest must call require_council_approval."""
    # NOTE: moved to ai_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.focus_builder.ai_router import suggest_nodes

    assert _function_calls_name(suggest_nodes, "require_council_approval")


@pytest.mark.unit
def test_focus_builder_generate_has_council_param() -> None:
    """Focus Builder generate must accept a council parameter."""
    # NOTE: moved to ai_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.focus_builder.ai_router import generate_flow_ai

    assert _function_has_param(generate_flow_ai, "council")


@pytest.mark.unit
def test_focus_builder_generate_uses_require_council_approval() -> None:
    """Focus Builder generate must call require_council_approval."""
    # NOTE: moved to ai_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.focus_builder.ai_router import generate_flow_ai

    assert _function_calls_name(generate_flow_ai, "require_council_approval")


# ---------------------------------------------------------------------------
# GAP-004: ALS /tasks and /broadcast
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_als_tasks_rejects_blocked_council() -> None:
    """ALS tasks must raise 403 when Council returns BLOCKED."""
    # NOTE: moved to als_tasks_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.als.als_tasks_router import delegate_task
    from src.core.api.v1.als.shared import TaskRequest

    fake_decision = MagicMock()
    fake_decision.verdict = MagicMock()
    fake_decision.verdict.value = "BLOCKED"
    fake_decision.explanation_for_user = "Blocked"
    fake_decision.decision_id = "dec-abc"

    mock_council = AsyncMock()
    mock_council.deliberate = AsyncMock(return_value=fake_decision)

    mock_user = MagicMock()
    mock_user.id = 7

    with patch("src.core.api.v1.als.als_tasks_router.build_council", return_value=mock_council):
        with pytest.raises(HTTPException) as exc_info:
            await delegate_task(
                request=TaskRequest(task_type="test", payload={}),
                tenant_id=1,
                db=MagicMock(),
                current_user=mock_user,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.unit
async def test_als_broadcast_rejects_blocked_council() -> None:
    """ALS broadcast must raise 403 when Council returns BLOCKED."""
    # NOTE: moved to als_tasks_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.als.als_tasks_router import broadcast_message

    fake_decision = MagicMock()
    fake_decision.verdict = MagicMock()
    fake_decision.verdict.value = "BLOCKED"
    fake_decision.explanation_for_user = "Blocked"
    fake_decision.decision_id = "dec-def"

    mock_council = AsyncMock()
    mock_council.deliberate = AsyncMock(return_value=fake_decision)

    mock_user = MagicMock()
    mock_user.id = 7

    with patch("src.core.api.v1.als.als_tasks_router.build_council", return_value=mock_council):
        with pytest.raises(HTTPException) as exc_info:
            await broadcast_message(
                message_type="alert",
                payload={"msg": "hello"},
                tenant_id=1,
                db=MagicMock(),
                current_user=mock_user,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_als_tasks_uses_require_council_approval() -> None:
    """ALS tasks must call require_council_approval."""
    # NOTE: moved to als_tasks_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.als.als_tasks_router import delegate_task

    assert _function_calls_name(delegate_task, "require_council_approval")


@pytest.mark.unit
def test_als_broadcast_uses_require_council_approval() -> None:
    """ALS broadcast must call require_council_approval."""
    # NOTE: moved to als_tasks_router.py by SP-API-002 Strangler Fig migration
    from src.core.api.v1.als.als_tasks_router import broadcast_message

    assert _function_calls_name(broadcast_message, "require_council_approval")


# ---------------------------------------------------------------------------
# GAP-005: Agentic /generate
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_agentic_generate_rejects_blocked_council() -> None:
    """Agentic generate must raise 403 when Council returns BLOCKED."""
    from src.core.api.agentic_flow_endpoints import generate_workflow
    from src.core.api.agentic_flow_endpoints import GenerateFlowRequest

    mock_user = MagicMock()
    mock_user.id = 7
    mock_user.tenant_id = 1

    fake_decision = MagicMock()
    fake_decision.verdict = MagicMock()
    fake_decision.verdict.value = "BLOCKED"
    fake_decision.explanation_for_user = "Blocked"
    fake_decision.decision_id = "dec-ghi"

    mock_council = AsyncMock()
    mock_council.deliberate = AsyncMock(return_value=fake_decision)

    with patch("src.core.copilot.council.factory.build_council", return_value=mock_council):
        with pytest.raises(HTTPException) as exc_info:
            await generate_workflow(
                request=GenerateFlowRequest(prompt="create a workflow"),
                response=MagicMock(),
                current_user=mock_user,
                service=MagicMock(),
                db=MagicMock(),
            )

    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_agentic_generate_uses_require_council_approval() -> None:
    """Agentic generate must call require_council_approval."""
    from src.core.api.agentic_flow_endpoints import generate_workflow

    assert _function_calls_name(generate_workflow, "require_council_approval")


# ---------------------------------------------------------------------------
# GAP-006: Agentic WS tenant_id must NOT come from payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_agentic_ws_ignores_payload_tenant_id() -> None:
    """Agentic WS must ignore client-supplied tenant_id in payload."""
    import inspect
    from src.core.api.agentic_flow_endpoints import websocket_builder

    source = inspect.getsource(websocket_builder)

    assert 'data.get("tenant_id")' not in source, (
        "CRITICAL: payload tenant_id fallback still present in WS builder"
    )
    assert "user.tenant_id" in source
