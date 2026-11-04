# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/workflow/ (SP-API-003)
"""
Workflow Suggestions API Endpoints
==================================

Production-ready REST API endpoints for AI-powered workflow suggestions.

Features:
- Pattern-based next node suggestions
- Workflow variant generation with tradeoffs
- Multi-tenant isolation (JWT + tenant context)
- RBAC enforcement via OAuth2 scopes

Endpoints:
- GET /api/v1/workflows/{id}/suggestions - Get AI suggestions for next nodes
- GET /api/v1/workflows/{id}/variants - Generate workflow variants with tradeoffs

Security: JWT required, tenant isolated, scope validated
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.core.workflow.models import C7Workflow as Workflow

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import require_scopes, OAuth2Scope
from src.core.middleware.tenant_context import get_current_tenant_id

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================


class SuggestionCategory(str, Enum):
    """Category of workflow suggestion"""

    ERROR = "error"
    COMPLIANCE = "compliance"
    STRUCTURE = "structure"
    OPTIMIZATION = "optimization"
    INTEGRATION = "integration"


class SuggestionPriority(str, Enum):
    """Priority level of suggestion"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VariantStrategy(str, Enum):
    """Variant optimization strategy"""

    COST_OPTIMIZED = "cost_optimized"
    SPEED_OPTIMIZED = "speed_optimized"
    RELIABILITY_OPTIMIZED = "reliability_optimized"


# ============================================================================
# Pydantic Models - Suggestions
# ============================================================================


class NodeSuggestion(BaseModel):
    """Suggested node to add to workflow"""

    id: str = Field(..., description="Unique suggestion ID")
    node_type: str = Field(..., description="Type of node (filter, transform, webhook, etc.)")
    label: str = Field(..., description="Human-readable label for the node")
    description: str = Field(..., description="Why this node is suggested")
    config_template: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Default configuration template"
    )
    insert_after: str | None = Field(None, description="Node ID to insert after")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")


class WorkflowSuggestion(BaseModel):
    """A single workflow improvement suggestion"""

    id: str = Field(..., description="Unique suggestion ID")
    category: SuggestionCategory = Field(..., description="Suggestion category")
    priority: SuggestionPriority = Field(..., description="Priority level")
    title: str = Field(..., description="Short title")
    description: str = Field(..., description="Detailed description")
    reasoning: str = Field(..., description="Why this suggestion is made")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    impact: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Expected impact metrics"
    )  # TODO(TYPE): replace Any with concrete type
    suggested_nodes: list[NodeSuggestion] = Field(default_factory=list, description="Nodes to add")
    affected_node_ids: list[str] = Field(
        default_factory=list, description="Existing nodes affected"
    )
    auto_applicable: bool = Field(False, description="Can be applied automatically")


class WorkflowSuggestionsResponse(BaseModel):
    """Response containing all suggestions for a workflow"""

    workflow_id: str
    workflow_name: str
    suggestions: list[WorkflowSuggestion]
    total_count: int
    generated_at: str
    model_version: str = "1.0.0"


# ============================================================================
# Pydantic Models - Variants
# ============================================================================


class VariantMetrics(BaseModel):
    """Metrics for a workflow variant"""

    estimated_cost_usd: float = Field(..., description="Estimated cost per execution")
    estimated_duration_ms: int = Field(..., description="Estimated duration in milliseconds")
    reliability_score: float = Field(..., ge=0.0, le=1.0, description="Reliability score 0-1")
    complexity_score: float = Field(..., ge=0.0, le=1.0, description="Complexity score 0-1")
    resource_usage: dict[str, float] = Field(
        default_factory=dict, description="Resource usage breakdown"
    )


class VariantTradeoff(BaseModel):
    """Trade-off explanation for a variant"""

    metric: str = Field(..., description="Metric name (cost, speed, reliability)")
    change_percent: float = Field(..., description="Percentage change from baseline")
    explanation: str = Field(..., description="Why this trade-off exists")
    is_improvement: bool = Field(..., description="True if this is an improvement")


class WorkflowVariant(BaseModel):
    """A workflow variant with different optimization"""

    id: str = Field(..., description="Unique variant ID")
    name: str = Field(..., description="Variant name")
    strategy: VariantStrategy = Field(..., description="Optimization strategy")
    description: str = Field(..., description="What makes this variant different")
    is_recommended: bool = Field(False, description="Is this the recommended variant")
    metrics: VariantMetrics = Field(..., description="Performance metrics")
    tradeoffs: list[VariantTradeoff] = Field(
        default_factory=list, description="Trade-offs vs baseline"
    )
    changes: list[dict[str, Any]] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list, description="Changes from original"
    )  # TODO(TYPE): replace Any with concrete type
    spec_json: dict[str, Any] = Field(
        default_factory=dict, description="Modified workflow spec"
    )  # TODO(TYPE): replace Any with concrete type


class WorkflowVariantsResponse(BaseModel):
    """Response containing workflow variants"""

    workflow_id: str
    workflow_name: str
    baseline_metrics: VariantMetrics
    variants: list[WorkflowVariant]
    generated_at: str
    model_version: str = "1.0.0"


# ============================================================================
# Router
# ============================================================================

router = APIRouter(prefix="/api/v1/workflows/suggestions", tags=["workflow-suggestions"])


# ============================================================================
# Helper Functions
# ============================================================================


async def get_tenant() -> int:
    """Get tenant ID with error handling"""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


async def get_workflow_by_id(workflow_id: str, tenant_id: int, db: AsyncSession) -> "Workflow":
    """Fetch workflow with tenant isolation"""
    from src.core.workflow.models import C7Workflow as Workflow  # lazy -- ADR-033

    query = select(Workflow).where(
        and_(
            Workflow.workflow_id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.is_active,
        )
    )
    result = await db.execute(query)
    workflow = result.scalars().first()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow '%s' not found or not active" % workflow_id,
        )
    return workflow


def analyze_workflow_patterns(
    spec: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> list[WorkflowSuggestion]:  # TODO(TYPE): replace Any with concrete type
    """
    Analyze workflow spec and generate suggestions based on patterns.
    """
    suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    tasks = spec.get("tasks", [])

    has_error_handler = any(
        t.get("type") == "error_handler" or "error" in t.get("ref", "").lower() for t in tasks
    )
    if not has_error_handler and len(tasks) > 2:
        suggestions.append(
            WorkflowSuggestion(
                id="suggestion_error_001",
                category=SuggestionCategory.ERROR,
                priority=SuggestionPriority.HIGH,
                title="Add Error Handler",
                description="This workflow lacks an error handling node. Add one to gracefully handle failures.",
                reasoning="Workflows without error handlers can fail silently, making debugging difficult.",
                confidence=0.92,
                impact={"reliability_improvement": 0.35, "debugging_time_saved_hours": 2.5},
                suggested_nodes=[
                    NodeSuggestion(
                        id="node_error_handler",
                        node_type="error_handler",
                        label="Error Handler",
                        description="Catches and logs errors from upstream nodes",
                        config_template={
                            "retry_count": 3,
                            "retry_delay_ms": 1000,
                            "fallback_action": "log_and_continue",
                        },
                        insert_after=None,
                        confidence=0.92,
                    )
                ],
                auto_applicable=True,
            )
        )

    has_audit = any(
        "audit" in t.get("ref", "").lower()
        or "compliance" in t.get("ref", "").lower()
        or t.get("type") == "audit"
        for t in tasks
    )
    if not has_audit:
        suggestions.append(
            WorkflowSuggestion(
                id="suggestion_compliance_001",
                category=SuggestionCategory.COMPLIANCE,
                priority=SuggestionPriority.MEDIUM,
                title="Add Audit Logging",
                description="Add an audit node to track workflow executions for compliance.",
                reasoning="GDPR and SOC2 require audit trails for data processing workflows.",
                confidence=0.87,
                impact={"compliance_score_improvement": 0.25, "audit_readiness": True},
                suggested_nodes=[
                    NodeSuggestion(
                        id="node_audit_log",
                        node_type="audit",
                        label="Audit Logger",
                        description="Records execution details for compliance",
                        config_template={
                            "log_level": "INFO",
                            "include_input": True,
                            "include_output": True,
                            "retention_days": 90,
                        },
                        insert_after=None,
                        confidence=0.87,
                    )
                ],
                auto_applicable=True,
            )
        )

    sequential_independent: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for i, task in enumerate(tasks):
        deps = task.get("depends_on", [])
        if i > 0 and not deps:
            sequential_independent.append(task.get("ref", "task_%s" % i))

    if len(sequential_independent) >= 2:
        suggestions.append(
            WorkflowSuggestion(
                id="suggestion_optimization_001",
                category=SuggestionCategory.OPTIMIZATION,
                priority=SuggestionPriority.MEDIUM,
                title="Parallelize Independent Tasks",
                description="Tasks %s appear to be independent and could run in parallel."
                % ", ".join(sequential_independent[:3]),
                reasoning="Running independent tasks in parallel reduces total execution time.",
                confidence=0.78,
                impact={"time_reduction_percent": 40, "resource_increase_percent": 20},
                affected_node_ids=sequential_independent[:5],
                auto_applicable=False,
            )
        )

    has_validation = any(
        "valid" in t.get("ref", "").lower() or t.get("type") in ("validator", "schema_check")
        for t in tasks
    )
    if not has_validation and len(tasks) > 1:
        suggestions.append(
            WorkflowSuggestion(
                id="suggestion_structure_001",
                category=SuggestionCategory.STRUCTURE,
                priority=SuggestionPriority.MEDIUM,
                title="Add Input Validation",
                description="Add a validation node at the start to ensure input data meets requirements.",
                reasoning="Early validation prevents downstream failures and improves data quality.",
                confidence=0.85,
                impact={"error_reduction_percent": 30, "data_quality_improvement": 0.2},
                suggested_nodes=[
                    NodeSuggestion(
                        id="node_validator",
                        node_type="validator",
                        label="Input Validator",
                        description="Validates input data against schema",
                        config_template={"schema": {}, "strict_mode": True, "on_failure": "reject"},
                        insert_after=None,
                        confidence=0.85,
                    )
                ],
                auto_applicable=True,
            )
        )

    has_notification = any(
        t.get("type") in ("webhook", "notification", "email")
        or "notify" in t.get("ref", "").lower()
        for t in tasks
    )
    if not has_notification and len(tasks) > 3:
        suggestions.append(
            WorkflowSuggestion(
                id="suggestion_integration_001",
                category=SuggestionCategory.INTEGRATION,
                priority=SuggestionPriority.LOW,
                title="Add Completion Notification",
                description="Add a webhook or notification node to alert when workflow completes.",
                reasoning="Notifications improve workflow visibility and enable downstream integrations.",
                confidence=0.75,
                impact={
                    "visibility_improvement": True,
                    "integration_potential": ["Slack", "Email", "Webhook"],
                },
                suggested_nodes=[
                    NodeSuggestion(
                        id="node_webhook",
                        node_type="webhook",
                        label="Completion Webhook",
                        description="Sends webhook notification on completion",
                        config_template={
                            "url": "",
                            "method": "POST",
                            "headers": {"Content-Type": "application/json"},
                            "include_result": True,
                        },
                        insert_after=None,
                        confidence=0.75,
                    )
                ],
                auto_applicable=False,
            )
        )

    return suggestions


def generate_workflow_variants(
    workflow: "Workflow",
    spec: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> tuple[VariantMetrics, list[WorkflowVariant]]:
    """Generate workflow variants with different optimization strategies."""
    tasks = spec.get("tasks", [])
    task_count = len(tasks)

    baseline = VariantMetrics(
        estimated_cost_usd=round(0.001 * task_count, 4),
        estimated_duration_ms=500 * task_count,
        reliability_score=0.85,
        complexity_score=min(1.0, task_count * 0.1),
        resource_usage={
            "cpu_percent": 20 + task_count * 5,
            "memory_mb": 128 + task_count * 32,
            "network_calls": task_count,
        },
    )

    variants: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    cost_optimized_spec = spec.copy()
    cost_optimized_spec["execution_mode"] = "sequential"
    cost_optimized_spec["resource_class"] = "small"

    variants.append(
        WorkflowVariant(
            id="variant_cost_001",
            name="Cost Optimized",
            strategy=VariantStrategy.COST_OPTIMIZED,
            description="Uses sequential execution and smaller resource allocation to minimize cost.",
            is_recommended=False,
            metrics=VariantMetrics(
                estimated_cost_usd=round(baseline.estimated_cost_usd * 0.6, 4),
                estimated_duration_ms=int(baseline.estimated_duration_ms * 1.8),
                reliability_score=0.82,
                complexity_score=baseline.complexity_score * 0.9,
                resource_usage={
                    "cpu_percent": baseline.resource_usage.get("cpu_percent", 25) * 0.5,
                    "memory_mb": baseline.resource_usage.get("memory_mb", 160) * 0.5,
                    "network_calls": baseline.resource_usage.get("network_calls", 5),
                },
            ),
            tradeoffs=[
                VariantTradeoff(
                    metric="cost",
                    change_percent=-40,
                    explanation="Sequential execution uses fewer concurrent resources",
                    is_improvement=True,
                ),
                VariantTradeoff(
                    metric="duration",
                    change_percent=80,
                    explanation="Sequential execution takes longer than parallel",
                    is_improvement=False,
                ),
                VariantTradeoff(
                    metric="reliability",
                    change_percent=-3.5,
                    explanation="Smaller resources may hit limits under load",
                    is_improvement=False,
                ),
            ],
            changes=[
                {
                    "type": "config",
                    "path": "execution_mode",
                    "old": "parallel",
                    "new": "sequential",
                },
                {"type": "config", "path": "resource_class", "old": "medium", "new": "small"},
            ],
            spec_json=cost_optimized_spec,
        )
    )

    speed_optimized_spec = spec.copy()
    speed_optimized_spec["execution_mode"] = "parallel"
    speed_optimized_spec["resource_class"] = "large"
    speed_optimized_spec["timeout"] = spec.get("timeout", 3600) // 2

    variants.append(
        WorkflowVariant(
            id="variant_speed_001",
            name="Speed Optimized",
            strategy=VariantStrategy.SPEED_OPTIMIZED,
            description="Maximizes parallelization and uses larger resources for fastest execution.",
            is_recommended=True,
            metrics=VariantMetrics(
                estimated_cost_usd=round(baseline.estimated_cost_usd * 1.8, 4),
                estimated_duration_ms=int(baseline.estimated_duration_ms * 0.4),
                reliability_score=0.88,
                complexity_score=baseline.complexity_score * 1.1,
                resource_usage={
                    "cpu_percent": baseline.resource_usage.get("cpu_percent", 25) * 2,
                    "memory_mb": baseline.resource_usage.get("memory_mb", 160) * 2,
                    "network_calls": baseline.resource_usage.get("network_calls", 5),
                },
            ),
            tradeoffs=[
                VariantTradeoff(
                    metric="duration",
                    change_percent=-60,
                    explanation="Parallel execution with more resources completes faster",
                    is_improvement=True,
                ),
                VariantTradeoff(
                    metric="cost",
                    change_percent=80,
                    explanation="Larger resources and parallelization cost more",
                    is_improvement=False,
                ),
                VariantTradeoff(
                    metric="reliability",
                    change_percent=3.5,
                    explanation="More resources provide better stability",
                    is_improvement=True,
                ),
            ],
            changes=[
                {
                    "type": "config",
                    "path": "execution_mode",
                    "old": "sequential",
                    "new": "parallel",
                },
                {"type": "config", "path": "resource_class", "old": "medium", "new": "large"},
                {
                    "type": "config",
                    "path": "timeout",
                    "old": spec.get("timeout", 3600),
                    "new": spec.get("timeout", 3600) // 2,
                },
            ],
            spec_json=speed_optimized_spec,
        )
    )

    reliability_optimized_spec = spec.copy()
    reliability_optimized_spec["retry_policy"] = {
        "max_retries": 5,
        "backoff_multiplier": 2,
        "initial_delay_ms": 1000,
    }
    reliability_optimized_spec["checkpoint_enabled"] = True
    reliability_optimized_spec["dead_letter_queue"] = True

    variants.append(
        WorkflowVariant(
            id="variant_reliability_001",
            name="Reliability Optimized",
            strategy=VariantStrategy.RELIABILITY_OPTIMIZED,
            description="Adds retries, checkpointing, and dead letter queue for maximum reliability.",
            is_recommended=False,
            metrics=VariantMetrics(
                estimated_cost_usd=round(baseline.estimated_cost_usd * 1.3, 4),
                estimated_duration_ms=int(baseline.estimated_duration_ms * 1.2),
                reliability_score=0.97,
                complexity_score=baseline.complexity_score * 1.2,
                resource_usage={
                    "cpu_percent": baseline.resource_usage.get("cpu_percent", 25) * 1.1,
                    "memory_mb": baseline.resource_usage.get("memory_mb", 160) * 1.3,
                    "network_calls": int(baseline.resource_usage.get("network_calls", 5) * 1.5),
                },
            ),
            tradeoffs=[
                VariantTradeoff(
                    metric="reliability",
                    change_percent=14,
                    explanation="Retries and checkpointing recover from transient failures",
                    is_improvement=True,
                ),
                VariantTradeoff(
                    metric="cost",
                    change_percent=30,
                    explanation="Checkpointing and retries add overhead",
                    is_improvement=False,
                ),
                VariantTradeoff(
                    metric="duration",
                    change_percent=20,
                    explanation="Checkpointing adds latency; retries may extend duration",
                    is_improvement=False,
                ),
            ],
            changes=[
                {
                    "type": "config",
                    "path": "retry_policy",
                    "old": None,
                    "new": {"max_retries": 5, "backoff_multiplier": 2},
                },
                {"type": "config", "path": "checkpoint_enabled", "old": False, "new": True},
                {"type": "config", "path": "dead_letter_queue", "old": False, "new": True},
            ],
            spec_json=reliability_optimized_spec,
        )
    )

    return baseline, variants


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/{workflow_id}/suggestions",
    response_model=WorkflowSuggestionsResponse,
    summary="Get AI suggestions for workflow improvements",
)
async def get_workflow_suggestions(
    workflow_id: str,
    category: SuggestionCategory | None = Query(None, description="Filter by category"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_READ)
    ),  # TODO(TYPE): replace Any with concrete type
) -> WorkflowSuggestionsResponse:
    """Get AI-powered suggestions for improving a workflow."""
    logger.info(
        "Getting workflow suggestions",
        extra={
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
            "category_filter": category,
            "min_confidence": min_confidence,
        },
    )

    workflow = await get_workflow_by_id(workflow_id, tenant_id, db)

    spec: dict[str, Any] = workflow.spec_json or {}  # TODO(TYPE): replace Any with concrete type
    suggestions = analyze_workflow_patterns(spec)

    if category:
        suggestions = [s for s in suggestions if s.category == category]

    suggestions = [s for s in suggestions if s.confidence >= min_confidence]

    priority_order = {
        SuggestionPriority.CRITICAL: 0,
        SuggestionPriority.HIGH: 1,
        SuggestionPriority.MEDIUM: 2,
        SuggestionPriority.LOW: 3,
    }
    suggestions.sort(key=lambda s: (priority_order.get(s.priority, 99), -s.confidence))
    suggestions = suggestions[:limit]

    return WorkflowSuggestionsResponse(
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.name,
        suggestions=suggestions,
        total_count=len(suggestions),
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_version="1.0.0",
    )


@router.get(
    "/{workflow_id}/variants",
    response_model=WorkflowVariantsResponse,
    summary="Generate workflow optimization variants",
)
async def get_workflow_variants(
    workflow_id: str,
    strategies: list[VariantStrategy] | None = Query(
        None, description="Specific strategies to generate (default: all)"
    ),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_READ)
    ),  # TODO(TYPE): replace Any with concrete type
) -> WorkflowVariantsResponse:
    """Generate workflow variants with different optimization strategies."""
    logger.info(
        "Generating workflow variants",
        extra={"workflow_id": workflow_id, "tenant_id": tenant_id, "strategies": strategies},
    )

    workflow = await get_workflow_by_id(workflow_id, tenant_id, db)

    spec: dict[str, Any] = workflow.spec_json or {}  # TODO(TYPE): replace Any with concrete type
    baseline_metrics, variants = generate_workflow_variants(workflow, spec)

    if strategies:
        variants = [v for v in variants if v.strategy in strategies]

    return WorkflowVariantsResponse(
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.name,
        baseline_metrics=baseline_metrics,
        variants=variants,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_version="1.0.0",
    )
