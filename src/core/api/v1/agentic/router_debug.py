"""GunaRouter debugging and analytics endpoints."""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints

from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.exceptions import AuthError
from src.core.routing.layer1_keyword import KeywordRouter
from src.core.routing.router_orchestrator import GunaRouter, RouterRequest, RouterResponse
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/router", tags=["Router Debugging"])


# Models
class RouteDebugRequest(BaseModel):
    query: str = Field(max_length=1000)
    explain: bool = Field(default=False, description="Include detailed routing explanation")


class RouteDebugResponse(BaseModel):
    query: str
    final_supervisor: str
    confidence: float
    routing_path: list[str]
    layer_results: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    explanation: str | None = None
    latency_ms: int


class LayerStatus(BaseModel):
    layer: str
    status: str
    avg_latency_ms: float
    match_count: int


class RoutingStats(BaseModel):
    total_routes: int
    layer_distribution: dict[str, int]
    avg_confidence: float
    avg_latency_ms: float


class KeywordPattern(BaseModel):
    pattern: str
    supervisor: str
    match_count: int


class AdaptationRuleResponse(BaseModel):
    id: str
    rule_type: str
    trigger_keywords: list[str]
    target_supervisor: str
    confidence: float
    priority: int
    times_applied: int
    success_rate: float
    active: bool


def _get_routing_path(result: RouterResponse) -> list[str]:
    """Build routing path from layer_used."""
    path: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    if result.layer_used:
        path.append(result.layer_used)
    if result.target_supervisor:
        path.append(result.target_supervisor)
    return path


def _create_task_data(query: str, tenant_id: str) -> TaskData:
    """Create TaskData from query string."""
    return TaskData(
        title=query[:50], description=query, metadata={"text": query, "tenant_id": tenant_id}
    )


# Endpoints
@router.post("/debug", response_model=RouteDebugResponse)
async def debug_route(
    request: RouteDebugRequest,
    current_user: UserResponse = Depends(get_current_user),
) -> RouteDebugResponse:
    """Debug a routing decision with detailed layer information."""
    import time

    tenant_id_str = str(current_user.tenant_id)
    start_time = time.time()

    try:
        guna_router = GunaRouter()

        task_data = _create_task_data(request.query, tenant_id_str)
        route_request = RouterRequest(task=task_data, tenant_id=current_user.tenant_id)

        # Get final result
        result = await guna_router.route(route_request)

        # Collect layer-specific results
        layer_results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        # Layer 1: Keyword matching
        l1_target = guna_router.layer1.route(task_data)
        layer_results["layer1_keyword"] = {
            "matched": l1_target is not None,
            "supervisor": l1_target,
            "confidence": 1.0 if l1_target else 0,
        }

        # Layer 2: Pattern matching (not implemented yet)
        layer_results["layer2_pattern"] = {
            "matched": False,
            "supervisor": None,
            "confidence": 0,
            "entities": [],
        }

        # Layer 3: Semantic routing
        l3_target = await guna_router.layer3.route(task_data)
        layer_results["layer3_semantic"] = {
            "matched": l3_target is not None,
            "supervisor": l3_target,
            "configured": True,
        }

        latency_ms = int((time.time() - start_time) * 1000)

        routing_path = _get_routing_path(result)

        explanation = None
        if request.explain:
            explanation = f"""
Routing Explanation for '{request.query}':
1. Layer 1 (Keyword): {"Matched" if l1_target else "No match"}
   - Matched keyword: {l1_target or "N/A"}
2. Layer 2 (Pattern): Not implemented
   - Entities found: 0
3. Layer 3 (Semantic): {"Matched" if l3_target else "No match"}
   - Target: {l3_target or "N/A"}
4. Layer 4 (Meta/CVA): Fallback selected

Final decision: Route to {result.target_supervisor} with {result.confidence:.2%} confidence
            """.strip()

        return RouteDebugResponse(
            query=request.query,
            final_supervisor=result.target_supervisor,
            confidence=result.confidence,
            routing_path=routing_path,
            layer_results=layer_results,
            explanation=explanation,
            latency_ms=latency_ms,
        )

    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error("router debug failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/layers/status")
async def get_layer_status() -> list[LayerStatus]:
    """Get status of all routing layers."""
    # Placeholder - would query metrics database
    return [
        LayerStatus(layer="layer1_keyword", status="active", avg_latency_ms=2.5, match_count=1500),
        LayerStatus(layer="layer2_pattern", status="active", avg_latency_ms=15.3, match_count=800),
        LayerStatus(
            layer="layer3_semantic", status="not_configured", avg_latency_ms=0, match_count=0
        ),
        LayerStatus(layer="layer4_meta", status="active", avg_latency_ms=45.2, match_count=200),
    ]


@router.get("/stats")
async def get_routing_stats(
    hours: int = Query(default=24, ge=1, le=720),
    current_user: UserResponse = Depends(get_current_user),
) -> RoutingStats:
    """Get routing statistics.

    De tenant komt uit de JWT. Hier stond `tenant_id` uit de querystring, zonder authenticatie (CLAUDE.md,
    NOOIT-lijst; Gate 2 2026-10-19). Nu nog vaste placeholdercijfers; het filter op de tenant van de
    gebruiker komt zodra er echte cijfers zijn.
    """
    # Placeholder - would query from database, filtered on current_user.tenant_id
    return RoutingStats(
        total_routes=2500,
        layer_distribution={
            "layer1_keyword": 1500,
            "layer2_pattern": 600,
            "layer3_semantic": 0,
            "layer4_meta": 400,
        },
        avg_confidence=0.82,
        avg_latency_ms=18.5,
    )


@router.get("/patterns")
async def get_keyword_patterns() -> list[KeywordPattern]:
    """Get all keyword patterns used in Layer 1."""
    patterns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for pattern, supervisor in KeywordRouter.KEYWORDS.items():
        patterns.append(
            KeywordPattern(
                pattern=pattern,
                supervisor=supervisor,
                match_count=0,  # Would be populated from analytics
            )
        )

    return patterns


@router.get("/adaptations")
async def get_adaptation_rules(
    active_only: bool = True, min_confidence: float = 0.0
) -> list[AdaptationRuleResponse]:
    """Get all active adaptation rules."""
    # Placeholder - would query from learning database
    return [
        AdaptationRuleResponse(
            id="rule_001",
            rule_type="routing_correction",
            trigger_keywords=["tax", "vat", "belasting"],
            target_supervisor="finance.treasury.supervisor",
            confidence=0.9,
            priority=9,
            times_applied=15,
            success_rate=0.93,
            active=True,
        ),
        AdaptationRuleResponse(
            id="rule_002",
            rule_type="routing_correction",
            trigger_keywords=["employee", "hiring", "payroll"],
            target_supervisor="hr.culture.supervisor",
            confidence=0.85,
            priority=8,
            times_applied=12,
            success_rate=0.91,
            active=True,
        ),
    ]


@router.post("/test")
async def test_routing(
    queries: Annotated[
        list[Annotated[str, StringConstraints(max_length=1000)]], Body(min_length=1, max_length=20)
    ],
    current_user: UserResponse = Depends(get_current_user),
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Test routing for multiple queries at once.

    De tenant komt uit de JWT. Hier stond een `tenant_id` uit de querystring zonder authenticatie: wie die
    invulde, liet de routering (en sinds de tenantdeur ook het taalmodel en de sleutel) van een andere
    tenant lopen (Gate 2, 2026-10-19).
    """
    tenant_id = str(current_user.tenant_id)
    guna_router = GunaRouter()
    results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for query in queries:
        try:
            task_data = _create_task_data(query, tenant_id)
            request = RouterRequest(task=task_data, tenant_id=current_user.tenant_id)
            result = await guna_router.route(request)
            routing_path = _get_routing_path(result)

            results.append(
                {
                    "query": query,
                    "supervisor": result.target_supervisor,
                    "confidence": result.confidence,
                    "routing_path": routing_path,
                    "status": "success",
                }
            )
        except Exception as e:
            results.append({"query": query, "error": type(e).__name__, "status": "error"})

    return results


@router.get("/heatmap")
async def get_routing_heatmap(
    days: int = Query(default=7, ge=1, le=90),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get routing heatmap data for visualization (tenant uit de JWT, niet uit de querystring)."""
    # Placeholder - would generate from analytics data, filtered on current_user.tenant_id
    return {
        "period_days": days,
        "tenant_id": str(current_user.tenant_id),
        "heatmap": {
            "finance.treasury.supervisor": 1200,
            "hr.culture.supervisor": 800,
            "it.security.supervisor": 300,
            "legal.compliance.supervisor": 200,
            "cva.meta.supervisor": 400,
        },
        "hourly_distribution": [
            {"hour": 0, "count": 50},
            {"hour": 1, "count": 30},
            # ... etc
            {"hour": 23, "count": 45},
        ],
    }
