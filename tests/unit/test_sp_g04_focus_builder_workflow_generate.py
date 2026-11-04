"""
SP-G04: Focus Builder workflow-generatie end-to-end.

Tests verify:
1. WORKFLOW_SCHEMA (ReactFlowGraph) validates nodes/edges correctly
2. LLMService.complete_json() delegates to provider with schema
3. AgenticFlowService.generate_flow_from_prompt() uses complete_json()
4. Endpoint returns {"success": True, "data": {"react_flow_graph": {...}}}
5. Tenant isolation is preserved
6. LLM failures are handled gracefully
7. Council governance is enforced

Markers:
    @pytest.mark.unit
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter

from src.core.copilot.council.types import DecisionVerdict
from src.core.llm.llm_client import LLMMessage, LLMProvider, LLMResponse


@pytest.fixture(autouse=True, scope="module")
def _patch_limiter_for_sp_g04():
    """Disable rate limiting for all endpoint tests in this module."""
    original_limit = Limiter.limit

    def _no_op_limit(self, *args, **kwargs):
        def _decorator(f):
            return f

        return _decorator

    Limiter.limit = _no_op_limit
    yield
    Limiter.limit = original_limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_decision(verdict: DecisionVerdict, explanation: str = "Test") -> MagicMock:
    decision = MagicMock()
    decision.verdict = verdict
    decision.explanation_for_user = explanation
    decision.decision_id = "decision-uuid"
    return decision


def _make_app(council_mock: MagicMock) -> FastAPI:
    """Build minimal FastAPI app with focus-builder router and mocked deps."""
    from src.core.api.v1.focus_builder.router import router, get_focus_builder_service
    from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.auth.auth_service import UserResponse
    from src.core.middleware.rate_limiter import get_limiter
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from src.core.middleware.tenant_context import set_tenant_id

    app = FastAPI()

    @app.middleware("http")
    async def add_tenant(request: Request, call_next: Any) -> Any:
        set_tenant_id(10)
        return await call_next(request)

    # Use a unique key per REQUEST to avoid rate limit collisions.
    # key_func must accept (request) -- zero-arg lambda causes SlowAPI to fall back
    # to IP address, causing 429 after 3 requests from the same test client.
    from uuid import uuid4

    no_op_limiter = Limiter(key_func=lambda request: str(uuid4()), default_limits=[])
    app.state.limiter = no_op_limiter
    app.include_router(router, prefix="/api/v1")

    mock_user = UserResponse(
        id=1,
        email="test@example.com",
        tenant_id=10,
        is_superuser=False,
    )

    app.dependency_overrides[get_current_user_dependency] = lambda: mock_user
    app.dependency_overrides[get_focus_builder_service] = lambda: MagicMock()
    app.dependency_overrides[get_focus_builder_council] = lambda: council_mock
    app.dependency_overrides[get_limiter] = lambda: no_op_limiter

    return app


# ---------------------------------------------------------------------------
# 1. WORKFLOW_SCHEMA validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowGraphSchema:
    """ReactFlowGraph acts as WORKFLOW_SCHEMA for complete_json()."""

    def test_valid_graph_parses(self) -> None:
        """A valid graph with nodes and edges passes validation."""
        from src.domains.flows.models import ReactFlowGraph, ReactFlowNode, ReactFlowEdge

        graph = ReactFlowGraph(
            nodes=[
                ReactFlowNode(
                    id="n1", type="trigger", position={"x": 0, "y": 0}, data={"label": "Start"}
                ),
                ReactFlowNode(
                    id="n2",
                    type="action",
                    position={"x": 200, "y": 0},
                    data={"label": "Send Email"},
                ),
            ],
            edges=[
                ReactFlowEdge(id="e1", source="n1", target="n2"),
            ],
        )
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert graph.nodes[0].id == "n1"

    def test_duplicate_node_ids_rejected(self) -> None:
        """Duplicate node ids raise ValueError."""
        from src.domains.flows.models import ReactFlowGraph, ReactFlowNode

        with pytest.raises(ValueError, match="Duplicate node ids"):
            ReactFlowGraph(
                nodes=[
                    ReactFlowNode(id="n1", type="trigger", position={"x": 0, "y": 0}, data={}),
                    ReactFlowNode(id="n1", type="action", position={"x": 200, "y": 0}, data={}),
                ],
                edges=[],
            )

    def test_empty_graph_is_valid(self) -> None:
        """An empty graph with no nodes and no edges is valid."""
        from src.domains.flows.models import ReactFlowGraph

        graph = ReactFlowGraph(nodes=[], edges=[])
        assert graph.nodes == []
        assert graph.edges == []


# ---------------------------------------------------------------------------
# 2. LLMService.complete_json() delegation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLLMServiceCompleteJson:
    """LLMService exposes complete_json() that delegates to the provider client."""

    @pytest.mark.asyncio
    async def test_llm_service_has_complete_json_method(self) -> None:
        """LLMService must have a complete_json() method."""
        from src.core.llm.llm_service import LLMService

        service = LLMService()
        assert hasattr(service, "complete_json"), "LLMService missing complete_json method"

    @pytest.mark.asyncio
    async def test_llm_service_delegates_to_provider(self) -> None:
        """complete_json() calls provider.complete_json() with schema and messages."""
        from src.core.llm.llm_service import LLMService
        from src.domains.flows.models import ReactFlowGraph

        service = LLMService()
        service.initialized = True
        mock_provider = MagicMock()
        mock_provider.complete_json = AsyncMock(
            return_value=LLMResponse(
                content='{"nodes":[],"edges":[]}',
                model="deepseek-chat",
                provider="deepseek",
                success=True,
            )
        )
        service.providers = {LLMProvider.DEEPSEEK: mock_provider}
        service.default_provider = LLMProvider.DEEPSEEK

        messages = [LLMMessage(role="user", content="Generate a workflow")]
        result = await service.complete_json(
            messages=messages,
            schema=ReactFlowGraph,
            provider=LLMProvider.DEEPSEEK,
        )

        mock_provider.complete_json.assert_awaited_once()
        call_args = mock_provider.complete_json.call_args
        assert call_args.kwargs.get("schema") == ReactFlowGraph
        assert isinstance(result, LLMResponse)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_llm_service_returns_error_on_failure(self) -> None:
        """When provider fails, complete_json returns LLMResponse with success=False."""
        from src.core.llm.llm_service import LLMService
        from src.domains.flows.models import ReactFlowGraph

        service = LLMService()
        service.initialized = True
        mock_provider = MagicMock()
        mock_provider.complete_json = AsyncMock(
            return_value=LLMResponse(
                content="",
                model="deepseek-chat",
                provider="deepseek",
                success=False,
                error_message="Timeout",
            )
        )
        service.providers = {LLMProvider.DEEPSEEK: mock_provider}
        service.default_provider = LLMProvider.DEEPSEEK

        messages = [LLMMessage(role="user", content="Generate a workflow")]
        result = await service.complete_json(
            messages=messages,
            schema=ReactFlowGraph,
            provider=LLMProvider.DEEPSEEK,
        )

        assert result.success is False
        assert result.error_message == "Timeout"


# ---------------------------------------------------------------------------
# 3. AgenticFlowService uses complete_json()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgenticFlowServiceUsesCompleteJson:
    """AgenticFlowService.generate_flow_from_prompt() uses complete_json() not generate_response()."""

    @pytest.mark.asyncio
    async def test_generate_calls_complete_json(self) -> None:
        """generate_flow_from_prompt must call complete_json() on the LLM service."""
        from src.domains.flows.agentic_service import AgenticFlowService
        from src.domains.flows.models import ReactFlowGraph

        service = AgenticFlowService()
        mock_llm_service = MagicMock()
        mock_llm_service.complete_json = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "trigger_1",
                                "type": "trigger",
                                "position": {"x": 250, "y": 200},
                                "data": {"label": "Start"},
                            }
                        ],
                        "edges": [],
                    }
                ),
                model="deepseek-chat",
                provider="deepseek",
                success=True,
            )
        )

        with patch.object(service, "_get_llm", return_value=mock_llm_service):
            result = await service.generate_flow_from_prompt(
                prompt="Send an email when a form is submitted",
                tenant_id=10,
            )

        mock_llm_service.complete_json.assert_awaited_once()
        call_kwargs = mock_llm_service.complete_json.call_args.kwargs
        assert call_kwargs.get("schema") == ReactFlowGraph
        assert result["success"] is True
        assert "react_flow_graph" in result["data"]

    @pytest.mark.asyncio
    async def test_generate_returns_success_wrapper(self) -> None:
        """Result must be wrapped as {"success": True, "data": {"react_flow_graph": {...}}}."""
        from src.domains.flows.agentic_service import AgenticFlowService

        service = AgenticFlowService()
        mock_llm_service = MagicMock()
        mock_llm_service.complete_json = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "n1",
                                "type": "trigger",
                                "position": {"x": 0, "y": 0},
                                "data": {},
                            },
                            {
                                "id": "n2",
                                "type": "action",
                                "position": {"x": 200, "y": 0},
                                "data": {},
                            },
                        ],
                        "edges": [
                            {"id": "e1", "source": "n1", "target": "n2"},
                        ],
                    }
                ),
                model="deepseek-chat",
                provider="deepseek",
                success=True,
            )
        )

        with patch.object(service, "_get_llm", return_value=mock_llm_service):
            result = await service.generate_flow_from_prompt(
                prompt="Create a simple workflow",
                tenant_id=10,
            )

        assert result["success"] is True
        assert "data" in result
        graph = result["data"]["react_flow_graph"]
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

    @pytest.mark.asyncio
    async def test_generate_handles_llm_failure(self) -> None:
        """When LLM returns success=False, service returns error wrapper with code."""
        from src.domains.flows.agentic_service import AgenticFlowService

        service = AgenticFlowService()
        mock_llm_service = MagicMock()
        mock_llm_service.complete_json = AsyncMock(
            return_value=LLMResponse(
                content="",
                model="deepseek-chat",
                provider="deepseek",
                success=False,
                error_message="Provider unavailable",
            )
        )

        with patch.object(service, "_get_llm", return_value=mock_llm_service):
            result = await service.generate_flow_from_prompt(
                prompt="Create a workflow",
                tenant_id=10,
            )

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "LLM_GENERATION_FAILED"
        assert result["error"]["message"] == "Het genereren van de workflow is mislukt."

    @pytest.mark.asyncio
    async def test_generate_includes_tenant_id_in_prompt_context(self) -> None:
        """tenant_id must be included in the messages passed to complete_json."""
        from src.domains.flows.agentic_service import AgenticFlowService

        service = AgenticFlowService()
        mock_llm_service = MagicMock()
        mock_llm_service.complete_json = AsyncMock(
            return_value=LLMResponse(
                content='{"nodes":[],"edges":[]}',
                model="deepseek-chat",
                provider="deepseek",
                success=True,
            )
        )

        with patch.object(service, "_get_llm", return_value=mock_llm_service):
            await service.generate_flow_from_prompt(
                prompt="Test",
                tenant_id=42,
            )

        call_args = mock_llm_service.complete_json.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        assert any("tenant_id" in m.content for m in messages), (
            "tenant_id must appear in at least one message content"
        )


# ---------------------------------------------------------------------------
# 4. Endpoint response wrapper and governance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateEndpointWrapper:
    """POST /api/v1/focus-builder/ai/generate returns wrapped response and enforces council."""

    def setup_method(self) -> None:
        """Maak de teller van de rate limiter leeg voor ELKE test in deze klasse.

        De decorator `@limiter.limit("3/minute")` op /ai/generate telt in de opslag van
        de module-brede limiter uit focus_builder/shared.py. Die opslag leeft zolang het
        proces leeft, dus verzoeken uit een ANDER testbestand tellen mee.

        WAAROM DIT ER ANDERS UITZIET DAN EERST. De vorige versie deed
        `if hasattr(limiter, "_storage") and ...: clear()`. `limiter` is echter een
        `_LazyLimiter`-proxy (shared.py:33) en die heeft GEEN `_storage` -- de echte
        slowapi-Limiter zit erachter, in `_limiter`. De voorwaarde was dus altijd False
        en deze setup deed NIETS, met een docstring erboven die het tegenovergestelde
        beweerde. Gemeten 2026-09-11:

            pytest tests/unit/test_focus_builder_ai_router_council_gate.py \
                   tests/unit/test_sp_g04_focus_builder_workflow_generate.py::TestGenerateEndpointWrapper
            -> 2 failed, "assert 429 == 403" -- de teller stond al op 3 door het andere bestand

        Los draaien was groen, en de volledige CI-selectie ook, omdat pytest-xdist de twee
        bestanden over verschillende werkprocessen verdeelt. Alleen een gerichte
        deelselectie legde het bloot -- precies de meting waarop een sprintdag zijn
        nulpunt baseert.

        Deze versie WEIGERT stil te falen: is de opslag niet te vinden, dan gaat de test
        eraan in plaats van door te lopen met een teller die niemand heeft geleegd.
        """
        from src.core.api.v1.focus_builder.shared import limiter

        echte_limiter = limiter._get_limiter()
        opslag = getattr(echte_limiter, "_storage", None)
        if opslag is None or not hasattr(opslag, "reset"):
            raise AssertionError(
                "De opslag van de rate limiter is niet te vinden achter de _LazyLimiter "
                f"(gevonden: {type(echte_limiter).__name__}, opslag: {type(opslag).__name__}). "
                "Zonder leegmaken telt dit bestand de verzoeken van andere bestanden mee en "
                "krijg je 429 in plaats van 403. Repareer dit in plaats van het over te slaan."
            )
        opslag.reset()

    def test_de_resetter_vindt_echt_de_gedeelde_teller(self) -> None:
        """Bindt setup_method aan de ECHTE opslag, zodat hij niet opnieuw hol kan worden."""
        from src.core.api.v1.focus_builder.shared import limiter

        opslag = limiter._get_limiter()._storage
        opslag.storage["toets-sleutel"] = 1
        self.setup_method()
        assert "toets-sleutel" not in opslag.storage

    def test_endpoint_returns_success_wrapper(self) -> None:
        """Endpoint returns {"success": True, "data": {"react_flow_graph": {...}}}."""
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_make_decision(DecisionVerdict.APPROVED))

        app = _make_app(council)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock(
                return_value={
                    "success": True,
                    "data": {
                        "react_flow_graph": {
                            "nodes": [
                                {
                                    "id": "n1",
                                    "type": "trigger",
                                    "position": {"x": 0, "y": 0},
                                    "data": {},
                                }
                            ],
                            "edges": [],
                        }
                    },
                }
            )
            mock_cls.return_value = mock_instance

            resp = client.post(
                "/api/v1/focus-builder/ai/generate", json={"prompt": "Create a workflow"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body
        assert "react_flow_graph" in body["data"]
        council.deliberate.assert_awaited_once()

    def test_endpoint_rejects_missing_prompt(self) -> None:
        """Missing prompt returns 400."""
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_make_decision(DecisionVerdict.APPROVED))

        app = _make_app(council)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/focus-builder/ai/generate", json={})

        assert resp.status_code == 400

    def test_endpoint_blocks_when_council_blocks(self) -> None:
        """Council BLOCKED verdict returns 403 with FLOW_BLOCKED_BY_COUNCIL code."""
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.BLOCKED, "Security policy violation")
        )

        app = _make_app(council)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock()
            mock_cls.return_value = mock_instance

            resp = client.post(
                "/api/v1/focus-builder/ai/generate", json={"prompt": "Create a workflow"}
            )

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "GOVERNANCE_BLOCKED"
        assert "Security policy violation" in detail["message"]
        mock_instance.generate_flow_from_prompt.assert_not_awaited()

    def test_endpoint_hitl_required_returns_403(self) -> None:
        """Council HITL_REQUIRED verdict returns 403 with decision_id."""
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, "Human review required")
        )

        app = _make_app(council)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock()
            mock_cls.return_value = mock_instance

            resp = client.post(
                "/api/v1/focus-builder/ai/generate", json={"prompt": "Create a workflow"}
            )

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "decision_id" in detail
        mock_instance.generate_flow_from_prompt.assert_not_awaited()
