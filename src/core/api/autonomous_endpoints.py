# orphan:exempt reason: legacy flat file, models/helpers re-used by src/core/api/v1/autonomous/ (SP-API-004)
#!/usr/bin/env python3
"""
Phase 4 - Autonomous Systems API Endpoints
Provides RESTful API for agent factory, self-healing, code generation, and emergent intelligence.
Legacy flat file: routes replaced by src/core/api/v1/autonomous/ (SP-API-004 Dag 5).
Models and helpers remain here for re-use by sub-routers.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope

from src.core.subagents.agent_factory import AgentType, get_agent_factory

# Compatibility alias for AgentArchetype (maps to AgentType)
AgentArchetype = AgentType

from src.core.autonomy.self_healing_system import get_self_healing_system
from src.core.emergence.emergent_intelligence import get_emergent_intelligence
from src.core.generation.dynamic_code_generator import get_code_generator

# PATTERN: Enum Validation & Exception Handling
# - All string inputs are validated against enum types (FailureType, CodeType, etc.)
# - HTTPException is caught separately to preserve status codes (404, 400, etc.)
# - Generic exceptions are caught last and converted to 500 errors
# This ensures proper error propagation and client-friendly error messages


# Additional type aliases for endpoint compatibility
class AgentTemplate(BaseModel):
    """Agent template definition (for endpoint compatibility)"""

    archetype: str
    name: str
    description: str
    core_capabilities: list[str]
    required_tools: list[str]
    performance_metrics: dict[str, float] = {}
    initialization_parameters: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class GenerationRequest(BaseModel):
    """Agent generation request for autonomous workflow"""

    request_id: str
    archetype: Any  # AgentType enum  # TODO(TYPE): replace Any with concrete type
    specialization: str
    performance_requirements: dict[str, float] = {}
    context_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    urgency_level: int = 4
    requester_agent: str = "api_endpoint"


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/autonomous", tags=["autonomous"])


def _extract_system_status(
    status_payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> str:  # TODO(TYPE): replace Any with concrete type
    """Normalize subsystem health payloads into a single status string."""
    return str(
        status_payload.get("overall_health")
        or status_payload.get("system_status")
        or status_payload.get("status")
        or "unknown"
    )


def _aggregate_overall_status(component_statuses: list[str]) -> str:
    """Compute an overall status from component-level status strings."""
    normalized = {status.lower() for status in component_statuses}
    if not normalized or normalized == {"unknown"}:
        return "unknown"
    if any(status in {"failed", "error", "unavailable"} for status in normalized):
        return "degraded"
    if any(status in {"degraded", "warning", "unknown"} for status in normalized):
        return "degraded"
    return "healthy"


# --- Pydantic Models ---


class AgentCreationRequest(BaseModel):
    archetype: str
    name: str
    description: str
    capabilities: list[str]
    tools: list[str]
    parameters: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class AgentTemplateModel(BaseModel):
    archetype: str
    name: str
    description: str
    core_capabilities: list[str]
    required_tools: list[str]
    performance_metrics: dict[str, float] = {}
    initialization_parameters: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class FailureReportModel(BaseModel):
    component: str
    failure_type: str
    severity: str
    description: str
    context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    auto_repair: bool = True


class CodeGenerationRequest(BaseModel):
    code_type: str
    functionality: str
    performance_constraints: dict[str, float] = {}
    integration_points: list[str] = []
    quality_requirements: dict[str, float] = {}
    security_constraints: list[str] = []
    strategy: str = "template_based"


class EmergenceFacilitationRequest(BaseModel):
    target_behavior: str
    participant_agents: list[str]
    conditions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    intelligence_level: int = 2


# --- Agent Factory Endpoints ---


@router.post("/agents/create")
async def create_autonomous_agent(
    request: AgentCreationRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a new autonomous agent dynamically using full GenerationRequest workflow.
    Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): dit is de legacy
    duplicaat van dezelfde route in src/core/api/v1/autonomous/agents_router.py
    (deze module is al gedocumenteerd als "Legacy flat file: routes replaced
    by src/core/api/v1/autonomous/"). Beide duplicaten konden een agent aanmaken
    zonder governance-check; beide zijn nu uitgeschakeld. Zie
    tests/architecture/test_agent_factory_governance_gate.py.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Autonomous agent creation is temporarily disabled pending a governance "
            "review (ADR-036 D12.5)."
        ),
    )


@router.get("/agents/templates")
async def get_agent_templates(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get available agent templates. Requires: AGENTS_READ"""
    try:
        factory = get_agent_factory()
        if factory is None:
            raise HTTPException(status_code=503, detail="Agent factory not available")
        templates = await factory.get_agent_templates()

        return {"templates": templates, "count": len(templates), "status": "success"}

    except HTTPException:
        # Een bewuste 503 ("not available") niet ompakken tot 500 (acceptant ronde 3, N4).
        raise
    except Exception as e:
        logger.error("get_agent_templates failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/agents/templates")
async def create_agent_template(
    template: AgentTemplateModel,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a new agent template. Requires: AGENTS_WRITE"""
    try:
        factory = get_agent_factory()
        if factory is None:
            raise HTTPException(status_code=503, detail="Agent factory not available")

        archetype = AgentArchetype(template.archetype.lower())

        agent_template = AgentTemplate(
            archetype=archetype,
            name=template.name,
            description=template.description,
            core_capabilities=template.core_capabilities,
            required_tools=template.required_tools,
            performance_metrics=template.performance_metrics,
            initialization_parameters=template.initialization_parameters,
        )

        template_id = await factory.register_template(agent_template)

        return {
            "success": True,
            "template_id": template_id,
            "archetype": template.archetype,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        # Een bewuste 503 ("not available") niet ompakken tot 500 (acceptant ronde 3, N4).
        raise
    except Exception as e:
        logger.error(f"Template creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/agents/factory/metrics")
async def get_factory_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get agent factory performance metrics. Requires: AGENTS_READ"""
    try:
        factory = get_agent_factory()
        if factory is None:
            raise HTTPException(status_code=503, detail="Agent factory not available")
        metrics = await factory.get_factory_metrics()

        return {
            "agents_created": metrics.get("total_agents_created", 0),
            "active_agents": metrics.get("active_agents", 0),
            "success_rate": metrics.get("creation_success_rate", 0.0),
            "avg_creation_time": metrics.get("avg_creation_time", 0.0),
            "templates_available": metrics.get("templates_count", 0),
            "archetypes_used": metrics.get("archetype_distribution", {}),
            "performance_metrics": metrics.get("performance_summary", {}),
        }

    except HTTPException:
        # Een bewuste 503 ("not available") niet ompakken tot 500 (acceptant ronde 3, N4).
        raise
    except Exception as e:
        logger.error(f"Failed to get factory metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


# --- Self-Healing System Endpoints ---


@router.post("/healing/report-failure")
async def report_system_failure(
    failure: FailureReportModel,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Report a system failure for autonomous healing. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): legacy duplicaat van
    src/core/api/v1/autonomous/healing_router.py, zelfde governance-gat.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Self-healing failure reporting is temporarily disabled pending a "
            "governance review (ADR-036 D12.5)."
        ),
    )


@router.get("/healing/status")
async def get_healing_system_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get self-healing system status and metrics. Requires: AGENTS_READ"""
    try:
        healing_system = get_self_healing_system()
        status = await healing_system.get_system_status()

        return {
            "overall_health": status.get("system_status", "unknown"),
            "active_failures": status.get("failure_history_count", 0),
            "repairs_in_progress": status.get("repairs_in_progress", 0),
            "repairs_completed": status.get("repair_history_count", 0),
            "success_rate": status.get("healing_metrics", {}).get("healing_success_rate", 0.0),
            "avg_repair_time": status.get("healing_metrics", {}).get("mean_time_to_repair", 0.0),
            "system_uptime": status.get("uptime", 0.0),
            "component_health": status.get("components", {}),
            "recent_failures": status.get("recent_failures", 0),
            "monitoring_active": status.get("monitoring_active", False),
            "registered_components": status.get("registered_components", 0),
            "emergency_protocols": status.get("emergency_protocols_available", 0),
        }

    except Exception as e:
        logger.error(f"Failed to get healing status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/healing/execute-repair/{failure_id}")
async def execute_repair(
    failure_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute repair plan for a specific failure. Requires: ADMIN_ALL

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): legacy duplicaat van
    src/core/api/v1/autonomous/healing_router.py, zelfde governance-gat.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Self-healing repair execution is temporarily disabled pending a "
            "governance review (ADR-036 D12.5)."
        ),
    )


# --- Dynamic Code Generation Endpoints ---


@router.post("/code/generate")
async def generate_code(
    request: CodeGenerationRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Generate code dynamically based on requirements. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): legacy duplicaat van
    src/core/api/v1/autonomous/code_router.py, zelfde governance-gat.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Dynamic code generation is temporarily disabled pending a governance "
            "review (ADR-036 D12.5)."
        ),
    )


@router.get("/code/templates")
async def get_code_templates(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get available code generation templates. Requires: AGENTS_READ"""
    try:
        code_generator = get_code_generator()
        templates = await code_generator.get_templates()

        return {
            "templates": templates,  # templates is already a list of dicts
            "count": len(templates),
        }

    except Exception as e:
        logger.error(f"Failed to get code templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/code/metrics")
async def get_generation_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get code generation performance metrics. Requires: AGENTS_READ"""
    """Get code generation performance metrics"""
    try:
        code_generator = get_code_generator()
        metrics = await code_generator.get_generation_metrics()

        return {
            "total_generations": metrics.get("total_generations", 0),
            "successful_generations": metrics.get("successful_generations", 0),
            "success_rate": metrics.get("success_rate", 0.0),
            "avg_generation_time": metrics.get("avg_generation_time", 0.0),
            "code_types_generated": metrics.get("code_type_distribution", {}),
            "quality_metrics": metrics.get("quality_summary", {}),
            "recent_generations": metrics.get("recent_generations", []),
        }

    except Exception as e:
        logger.error(f"Failed to get generation metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


# --- Emergent Intelligence Endpoints ---


@router.post("/emergence/facilitate")
async def facilitate_emergence(
    request: EmergenceFacilitationRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Facilitate emergent intelligence behaviors. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): legacy duplicaat van
    src/core/api/v1/autonomous/emergence_router.py, zelfde governance-gat.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Emergent intelligence facilitation is temporarily disabled pending a "
            "governance review (ADR-036 D12.5)."
        ),
    )


@router.get("/emergence/behaviors")
async def get_emergent_behaviors(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detected emergent behaviors. Requires: AGENTS_READ"""
    try:
        emergence_system = get_emergent_intelligence()
        behaviors = await emergence_system.get_detected_behaviors()

        return {
            "detected_behaviors": [
                {
                    "behavior_id": behavior.behavior_id,
                    "type": behavior.emergence_type.value,
                    "participants": behavior.participants,
                    "intelligence_level": behavior.intelligence_level.value,
                    "emergence_strength": behavior.emergence_strength,
                    "stability": behavior.stability_score,
                    "outcomes": behavior.observed_outcomes,
                    "discovered_at": behavior.emergence_timestamp.isoformat(),
                }
                for behavior in behaviors
            ],
            "count": len(behaviors),
        }

    except Exception as e:
        logger.error(f"Failed to get emergent behaviors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/emergence/intelligence-levels")
async def get_intelligence_analysis(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get system-wide intelligence level analysis. Requires: AGENTS_READ"""
    try:
        emergence_system = get_emergent_intelligence()
        analysis = await emergence_system.analyze_collective_intelligence()

        return {
            "collective_intelligence_level": analysis.get("collective_level", 0),
            "individual_levels": analysis.get("individual_levels", {}),
            "emerging_capabilities": analysis.get("new_capabilities", []),
            "intelligence_trends": analysis.get("trends", []),
            "complexity_metrics": analysis.get("complexity", {}),
            "adaptation_rate": analysis.get("adaptation_rate", 0.0),
            "innovation_potential": analysis.get("innovation_score", 0.0),
        }

    except Exception as e:
        logger.error(f"Failed to analyze intelligence levels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


# --- System Integration Endpoints ---


@router.get("/status")
async def get_autonomous_systems_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive status of all autonomous systems. Requires: AGENTS_READ"""
    try:
        # Get status from all Phase 4 systems
        factory = get_agent_factory()
        healing_system = get_self_healing_system()
        code_generator = get_code_generator()
        emergence_system = get_emergent_intelligence()

        if factory is None:
            raise HTTPException(status_code=503, detail="Agent factory not available")
        if healing_system is None:
            raise HTTPException(status_code=500, detail="Self healing system not available")
        if code_generator is None:
            raise HTTPException(status_code=500, detail="Code generator not available")
        if emergence_system is None:
            raise HTTPException(status_code=500, detail="Emergence system not available")

        factory_status = await factory.get_system_status()
        healing_status = await healing_system.get_system_status()
        generation_status = await code_generator.get_system_status()
        emergence_status = await emergence_system.get_system_status()

        return {
            "phase": "Phase 4 - Autonomous Systems",
            "overall_status": _aggregate_overall_status(
                [
                    _extract_system_status(factory_status),
                    _extract_system_status(healing_status),
                    _extract_system_status(generation_status),
                    _extract_system_status(emergence_status),
                ]
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "systems": {
                "agent_factory": {
                    "status": _extract_system_status(factory_status),
                    "agents_active": factory_status.get("active_agents", 0),
                    "templates_available": factory_status.get("templates_count", 0),
                },
                "self_healing": {
                    "status": _extract_system_status(healing_status),
                    "active_repairs": healing_status.get("repairs_in_progress", 0),
                    "system_uptime": healing_status.get("system_uptime", 0.0),
                },
                "code_generation": {
                    "status": _extract_system_status(generation_status),
                    "generations_completed": generation_status.get("total_generations", 0),
                    "success_rate": generation_status.get("success_rate", 0.0),
                },
                "emergent_intelligence": {
                    "status": _extract_system_status(emergence_status),
                    "behaviors_detected": emergence_status.get("behaviors_count", 0),
                    "intelligence_level": emergence_status.get("collective_intelligence", 1),
                },
            },
            "capabilities": [
                "Dynamic agent creation and management",
                "Autonomous failure detection and repair",
                "Real-time code generation and optimization",
                "Emergent intelligence facilitation",
                "Self-improving system architecture",
            ],
        }

    except HTTPException:
        # Een bewuste 503 ("not available") niet ompakken tot 500 (acceptant ronde 3, N4).
        raise
    except Exception as e:
        logger.error(f"Failed to get autonomous systems status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


# Health check for autonomous systems
@router.get("/health")
async def autonomous_health_check(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Health check for all Phase 4 autonomous systems. Requires: AGENTS_READ"""
    try:
        factory = get_agent_factory()
        healing_system = get_self_healing_system()
        code_generator = get_code_generator()
        emergence_system = get_emergent_intelligence()

        if factory is None:
            raise RuntimeError("Agent factory not available")
        if healing_system is None:
            raise RuntimeError("Self healing system not available")
        if code_generator is None:
            raise RuntimeError("Code generator not available")
        if emergence_system is None:
            raise RuntimeError("Emergence system not available")

        factory_status = _extract_system_status(await factory.get_system_status())
        healing_status = _extract_system_status(await healing_system.get_system_status())
        code_generation_status = _extract_system_status(await code_generator.get_system_status())
        emergence_status = _extract_system_status(await emergence_system.get_system_status())
        overall_status = _aggregate_overall_status(
            [
                factory_status,
                healing_status,
                code_generation_status,
                emergence_status,
            ]
        )

        return {
            "status": overall_status,
            "phase": "Phase 4 - Autonomous Systems",
            "components": {
                "agent_factory": factory_status,
                "self_healing": healing_status,
                "code_generation": code_generation_status,
                "emergent_intelligence": emergence_status,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "autonomy_level": "stub_phase4" if overall_status == "healthy" else "limited",
        }

    except Exception as e:
        logger.error(f"Autonomous health check failed: {e}", exc_info=True)
        return {
            "status": "degraded",
            "error": "Internal error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Background task initialization
async def initialize_autonomous_systems() -> bool:
    """Initialize all Phase 4 autonomous systems"""
    try:
        logger.info("Initializing Phase 4 autonomous systems...")

        # Initialize systems in dependency order
        factory = get_agent_factory()
        if factory is None:
            raise RuntimeError("Agent factory not available")
        await factory.start()

        healing_system = get_self_healing_system()
        await healing_system.start()  # NOTE: third-party lacks stubs

        code_generator = get_code_generator()
        await code_generator.start()  # NOTE: third-party lacks stubs

        emergence_system = get_emergent_intelligence()
        await emergence_system.start()  # NOTE: third-party lacks stubs

        logger.info("Phase 4 autonomous systems initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize autonomous systems: {e}")
        return False
