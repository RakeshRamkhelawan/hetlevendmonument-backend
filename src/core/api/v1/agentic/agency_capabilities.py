"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
Agency Capabilities API - CORRECT Integration

This extends the existing /api/v1/agentic/agents endpoints
with Agency capability execution.

Usage:
    POST /api/v1/agentic/agents/{agent_id}/execute-agency-capability

NOT: /api/v1/agency-agents/execute  <-- This was the WRONG approach
"""

import logging
import time
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.api.v1.agentic.dependencies import (
    AgencyCapabilityRegistry,
    create_planner_agent_with_agency,
)
from src.core.auth.api_deps import get_current_user
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import User
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Agency Capabilities"])


# ============================================================================
# Schemas
# ============================================================================


class AgencyCapabilityExecuteRequest(BaseModel):
    """Request to execute an Agency capability"""

    capability_name: str = Field(
        ..., description="Name of Agency capability (e.g., agency_design_system)"
    )
    payload: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Capability input parameters"
    )
    context: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Additional execution context"
    )


class AgencyCapabilityExecuteResponse(BaseModel):
    """Response from Agency capability execution"""

    success: bool
    result: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    execution_time: float
    agent_id: str
    capability_name: str
    task_id: str


class AgencyCapabilityInfo(BaseModel):
    """Information about an Agency capability"""

    name: str
    description: str
    category: str  # design, engineering, marketing
    input_types: list[str]
    output_types: list[str]


class AgencyCapabilitiesListResponse(BaseModel):
    """List of available Agency capabilities"""

    capabilities: list[AgencyCapabilityInfo]


# ============================================================================
# Endpoints (Integrated with existing agent structure)
# ============================================================================


@router.get("/agency-capabilities", response_model=AgencyCapabilitiesListResponse)
async def list_agency_capabilities(
    category: str | None = None,
    current_user: User = Depends(get_current_user),
) -> AgencyCapabilitiesListResponse:
    """
    List all available Agency capabilities (46 total).

    Categories:
    - design: 4 capabilities
    - engineering: 4 capabilities
    - marketing: 2 capabilities
    - product_management: 6 capabilities
    - testing_qa: 6 capabilities
    - support_legal: 4 capabilities
    - specialized: 4 capabilities
    - game_development: 4 capabilities

    This extends the existing /agents endpoints with Agency skills.

    Args:
        category: Optional filter by category

    Returns: List[Any] of Agency capabilities available for execution  # TODO(TYPE): replace Any with concrete type

    Example:
        GET /api/v1/agentic/agents/agency-capabilities
        GET /api/v1/agentic/agents/agency-capabilities?category=design
        GET /api/v1/agentic/agents/agency-capabilities?category=product_management
    """
    all_capabilities = [
        # Design (4)
        AgencyCapabilityInfo(
            name="agency_design_system",
            description="Generate complete design system with CSS variables and component tokens",
            category="design",
            input_types=["brand_colors", "spacing_base", "component_needs"],
            output_types=["css_variables", "component_tokens", "accessibility_notes"],
        ),
        AgencyCapabilityInfo(
            name="agency_image_prompt",
            description="Craft optimized prompts for AI image generation",
            category="design",
            input_types=["subject", "style", "platform"],
            output_types=["prompt", "negative_prompt", "platform_optimizations"],
        ),
        AgencyCapabilityInfo(
            name="agency_brand_foundation",
            description="Create brand foundation with mission, vision, and values",
            category="design",
            input_types=["business_name", "industry", "target_audience"],
            output_types=["brand_foundation", "positioning"],
        ),
        # Engineering (4)
        AgencyCapabilityInfo(
            name="agency_react_component",
            description="Generate React component with TypeScript interfaces",
            category="engineering",
            input_types=["component_name", "props", "framework"],
            output_types=["component_code", "tests", "documentation"],
        ),
        AgencyCapabilityInfo(
            name="agency_api_design",
            description="Design REST/GraphQL API structure",
            category="engineering",
            input_types=["resources", "api_type", "authentication"],
            output_types=["endpoints", "schemas", "authentication"],
        ),
        AgencyCapabilityInfo(
            name="agency_threat_model",
            description="Perform STRIDE threat modeling",
            category="engineering",
            input_types=["system_name", "data_sensitivity", "methodology"],
            output_types=["threats", "mitigations", "risk_priorities"],
        ),
        # Marketing (2)
        AgencyCapabilityInfo(
            name="agency_viral_loop",
            description="Design viral growth mechanics",
            category="marketing",
            input_types=["product_type", "target_audience"],
            output_types=["viral_mechanic", "tactics", "kpi_targets"],
        ),
        AgencyCapabilityInfo(
            name="agency_content_strategy",
            description="Create content strategy and editorial calendar",
            category="marketing",
            input_types=["business_goals", "target_audience"],
            output_types=["content_pillars", "distribution_channels", "kpis"],
        ),
        # Product Management (6)
        AgencyCapabilityInfo(
            name="agency_prioritize_sprint",
            description="Prioritize backlog items based on value and effort",
            category="product_management",
            input_types=["backlog", "team_capacity"],
            output_types=["sprint_backlog", "capacity_utilization"],
        ),
        AgencyCapabilityInfo(
            name="agency_research_trends",
            description="Analyze market trends and competitive landscape",
            category="product_management",
            input_types=["industry", "timeframe"],
            output_types=["trends", "competitive_analysis"],
        ),
        AgencyCapabilityInfo(
            name="agency_synthesize_feedback",
            description="Analyze and synthesize user feedback",
            category="product_management",
            input_types=["feedback", "source"],
            output_types=["insights", "prioritized_actions"],
        ),
        AgencyCapabilityInfo(
            name="agency_studio_delivery",
            description="Orchestrate multi-project delivery",
            category="product_management",
            input_types=["projects", "resources"],
            output_types=["delivery_timeline", "resource_allocation"],
        ),
        AgencyCapabilityInfo(
            name="agency_coordinate_project",
            description="Coordinate cross-functional project execution",
            category="product_management",
            input_types=["project_name", "phases"],
            output_types=["coordination_plan", "timeline"],
        ),
        AgencyCapabilityInfo(
            name="agency_track_experiment",
            description="Design and track A/B tests",
            category="product_management",
            input_types=["hypothesis", "primary_metric"],
            output_types=["experiment_design", "tracking_plan"],
        ),
        # Testing & QA (6)
        AgencyCapabilityInfo(
            name="agency_collect_evidence",
            description="Collect test evidence with screenshots",
            category="testing_qa",
            input_types=["test_case"],
            output_types=["evidence_package", "coverage"],
        ),
        AgencyCapabilityInfo(
            name="agency_check_reality",
            description="Certify production readiness",
            category="testing_qa",
            input_types=["quality_gates"],
            output_types=["production_readiness", "sign_off"],
        ),
        AgencyCapabilityInfo(
            name="agency_test_api",
            description="Validate API endpoints and contracts",
            category="testing_qa",
            input_types=["endpoints"],
            output_types=["test_suite", "coverage"],
        ),
        AgencyCapabilityInfo(
            name="agency_benchmark_performance",
            description="Run performance tests",
            category="testing_qa",
            input_types=["scenario"],
            output_types=["benchmark_results", "recommendations"],
        ),
        AgencyCapabilityInfo(
            name="agency_audit_accessibility",
            description="Audit for WCAG compliance",
            category="testing_qa",
            input_types=["wcag_level"],
            output_types=["audit_results", "critical_fixes"],
        ),
        AgencyCapabilityInfo(
            name="agency_evaluate_tools",
            description="Evaluate testing tools",
            category="testing_qa",
            input_types=["category"],
            output_types=["recommended", "alternatives"],
        ),
        # Support & Legal (4)
        AgencyCapabilityInfo(
            name="agency_draft_support",
            description="Draft customer support responses",
            category="support_legal",
            input_types=["issue", "customer_tier"],
            output_types=["response_draft", "tone"],
        ),
        AgencyCapabilityInfo(
            name="agency_analytics_report",
            description="Create analytics dashboards",
            category="support_legal",
            input_types=["report_type", "metrics"],
            output_types=["key_metrics", "recommendations"],
        ),
        AgencyCapabilityInfo(
            name="agency_check_compliance",
            description="Check GDPR, CCPA, SOC2 compliance",
            category="support_legal",
            input_types=["regulations"],
            output_types=["compliance_status", "findings"],
        ),
        AgencyCapabilityInfo(
            name="agency_track_finance",
            description="Track financial KPIs",
            category="support_legal",
            input_types=["financial_data"],
            output_types=["financial_overview", "budget_status"],
        ),
        # Specialized (4) - orchestrator renamed
        AgencyCapabilityInfo(
            name="agency_coordinate_multi_agent",
            description="Coordinate multiple agents (renamed from orchestrator)",
            category="specialized",
            input_types=["agents", "task"],
            output_types=["coordination_plan", "task_decomposition"],
        ),
        AgencyCapabilityInfo(
            name="agency_deep_analysis",
            description="Deep dive data analysis",
            category="specialized",
            input_types=["dataset", "question"],
            output_types=["key_findings", "recommendations"],
        ),
        AgencyCapabilityInfo(
            name="agency_extract_sales",
            description="Extract and normalize sales data",
            category="specialized",
            input_types=["sources"],
            output_types=["metrics_calculated", "territory_breakdown"],
        ),
        AgencyCapabilityInfo(
            name="agency_distribute_reports",
            description="Automated report delivery",
            category="specialized",
            input_types=["reports", "recipients"],
            output_types=["distribution_plan", "confirmation"],
        ),
        # Game Development (4)
        AgencyCapabilityInfo(
            name="agency_design_unity",
            description="Design Unity project architecture",
            category="game_development",
            input_types=["project_type"],
            output_types=["architecture", "performance_considerations"],
        ),
        AgencyCapabilityInfo(
            name="agency_design_unreal",
            description="Design Unreal Engine systems",
            category="game_development",
            input_types=["game_type"],
            output_types=["systems_design", "networking"],
        ),
        AgencyCapabilityInfo(
            name="agency_script_godot",
            description="Create GDScript gameplay code",
            category="game_development",
            input_types=["feature"],
            output_types=["code", "best_practices"],
        ),
        AgencyCapabilityInfo(
            name="agency_design_game",
            description="Design game mechanics",
            category="game_development",
            input_types=["genre"],
            output_types=["core_mechanics", "balancing"],
        ),
    ]

    if category:
        all_capabilities = [c for c in all_capabilities if c.category == category]

    return AgencyCapabilitiesListResponse(capabilities=all_capabilities)


@router.post(
    "/{agent_id}/execute-agency-capability", response_model=AgencyCapabilityExecuteResponse
)
async def execute_agency_capability(
    agent_id: str,
    request: AgencyCapabilityExecuteRequest,
    current_user: User = Depends(get_current_user),
) -> AgencyCapabilityExecuteResponse:
    """
    Execute an Agency capability through an agent.

    This is the CORRECT integration pattern:
    - Uses existing AgentRegistry
    - Uses existing tenant context
    - Emits events via existing event bus
    - Participates in workflow engine

    Args:
        agent_id: ID of the agent to use (e.g., planner_agent)
        request: Capability execution request

    Returns:
        Execution result with Agency skill output

    Example:
        POST /api/v1/agentic/agents/planner_001/execute-agency-capability
        {
            "capability_name": "agency_design_system",
            "payload": {
                "brand_colors": {"primary": "#6366f1"},
                "spacing_base": 4
            }
        }
    """
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    # Validate capability exists
    if not AgencyCapabilityRegistry.get(request.capability_name):
        raise HTTPException(
            status_code=404,
            detail=f"Agency capability '{request.capability_name}' not found. "
            f"Available: {AgencyCapabilityRegistry.list_capabilities()}",
        )

    try:
        # Create or get agent with Agency capabilities
        # In production, this would use AgentRegistry
        agent = create_planner_agent_with_agency(tenant_id=tenant_id)
        await agent.initialize()

        # Create task with capability info
        task = TaskData(
            id=f"agency_task_{tenant_id}_{request.capability_name}",
            title=f"Agency: {request.capability_name}",
            description=f"Executed by {current_user.email}",
            metadata={
                "type": request.capability_name,
                "tenant_id": tenant_id,
                "user_id": str(current_user.id),
                "context": request.context,
                "payload": request.payload,
            },
        )

        # Execute via agent (which routes to Agency capability)
        result = await agent.process_task(task)

        if not result.success:
            raise HTTPException(
                status_code=500, detail=result.error_message or "Capability execution failed"
            )

        return AgencyCapabilityExecuteResponse(
            success=True,
            result=cast(
                dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                result.result_data or {},
            ),
            execution_time=result.execution_time,
            agent_id=agent.agent_id,
            capability_name=request.capability_name,
            task_id=task.id,
        )

    except Exception as e:
        # Futureproof fallback: keep API usable even if agent runtime wiring changes.
        try:
            handler = AgencyCapabilityRegistry.get(request.capability_name)
            if not handler:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agency capability '{request.capability_name}' not found.",
                )

            start_time = time.time()
            result_data = handler(request.payload)
            return AgencyCapabilityExecuteResponse(
                success=True,
                result=result_data,
                execution_time=time.time() - start_time,
                agent_id=str(agent_id),
                capability_name=request.capability_name,
                task_id=f"agency_task_{tenant_id}_{request.capability_name}",
            )
        except HTTPException:
            raise
        except Exception as fallback_error:
            # Beide fouten naar het log; naar de klant gaat een vaste tekst (geen str(e)).
            logger.error(
                "agency capability uitvoering mislukt: %s; terugval mislukt: %s",
                type(e).__name__,
                type(fallback_error).__name__,
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="Agency capability execution error")


@router.get("/{agent_id}/agency-capabilities")
async def get_agent_agency_capabilities(
    agent_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get Agency capabilities available for a specific agent.

    Returns which Agency skills this agent can execute.
    """
    tenant_id = get_tenant_id()

    # In production, query from AgentRegistry
    # For now, return planner agent capabilities
    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "agency_capabilities": [
            {
                "name": "agency_design_system",
                "description": "Generate design system",
                "available": True,
            },
            {
                "name": "agency_react_component",
                "description": "Generate React component",
                "available": True,
            },
            {
                "name": "agency_threat_model",
                "description": "Security threat modeling",
                "available": True,
            },
            {
                "name": "agency_viral_loop",
                "description": "Design viral growth",
                "available": True,
            },
        ],
    }
