# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Agent Factory sub-router (ADR-033 Laag 1).

Routes: POST /agents/create, GET/POST /agents/templates,
        GET /agents/factory/metrics, GET /status, GET /health
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from src.core.api.dependencies import require_admin_user

from src.core.auth.api_deps import UserResponse, require_scopes, OAuth2Scope
from src.core.api.autonomous_endpoints import (
    AgentArchetype,
    AgentCreationRequest,
    AgentTemplate,
    AgentTemplateModel,
    _aggregate_overall_status,
    _extract_system_status,
)
from src.core.subagents.agent_factory import get_agent_factory
from src.core.autonomy.self_healing_system import get_self_healing_system
from src.core.generation.dynamic_code_generator import get_code_generator
from src.core.emergence.emergent_intelligence import get_emergent_intelligence

logger = logging.getLogger(__name__)

agents_router = APIRouter(prefix="/api/v1/autonomous")


@agents_router.post("/agents/create")
async def create_autonomous_agent(
    request: AgentCreationRequest,
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a new autonomous agent dynamically. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): dit pad kon een agent
    aanmaken zonder ooit GovernanceContract.is_action_permitted() aan te
    roepen. AgentFactory/BaseAgent (src/core/subagents/agent_factory.py)
    kennen tenant_id structureel niet, dus een governance-check "erbij
    plakken" vergt eerst een grotere uitbreiding. Geen vindbare caller in
    frontend, CI/CD of docs; de enige gevonden aanroeper was een OWASP-A5-
    regressietest (tests/unit/api/v1/test_no_dict_str_e_leak.py), die is
    aangepast op het nieuwe gedrag. Zie
    tests/architecture/test_agent_factory_governance_gate.py.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Autonomous agent creation is temporarily disabled pending a governance "
            "review (ADR-036 D12.5)."
        ),
    )


@agents_router.get("/agents/templates")
async def get_agent_templates(
    current_user: UserResponse = Depends(require_admin_user),
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


@agents_router.post("/agents/templates")
async def create_agent_template(
    template: AgentTemplateModel,
    current_user: UserResponse = Depends(require_admin_user),
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
        logger.error("Template creation failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@agents_router.get("/agents/factory/metrics")
async def get_factory_metrics(
    current_user: UserResponse = Depends(require_admin_user),
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
        logger.error("Failed to get factory metrics: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@agents_router.get("/status")
async def get_autonomous_systems_status(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive status of all autonomous systems. Requires: AGENTS_READ"""
    try:
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
        }
    except HTTPException:
        # Een bewuste 503 ("not available") niet ompakken tot 500 (acceptant ronde 3, N4).
        raise
    except Exception as e:
        logger.error(
            "Failed to get autonomous systems status: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal error") from e


@agents_router.get("/health")
async def autonomous_health_check(
    current_user: UserResponse = Depends(require_admin_user),
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

        factory_s = _extract_system_status(await factory.get_system_status())
        healing_s = _extract_system_status(await healing_system.get_system_status())
        codegen_s = _extract_system_status(await code_generator.get_system_status())
        emergence_s = _extract_system_status(await emergence_system.get_system_status())
        overall = _aggregate_overall_status([factory_s, healing_s, codegen_s, emergence_s])

        return {
            "status": overall,
            "phase": "Phase 4 - Autonomous Systems",
            "components": {
                "agent_factory": factory_s,
                "self_healing": healing_s,
                "code_generation": codegen_s,
                "emergent_intelligence": emergence_s,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "autonomy_level": "stub_phase4" if overall == "healthy" else "limited",
        }
    except Exception as e:
        logger.error("Autonomous health check failed: %s: %s", type(e).__name__, e, exc_info=True)
        return {
            "status": "degraded",
            "error": "Internal error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
