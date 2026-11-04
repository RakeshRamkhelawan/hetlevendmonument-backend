# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
Agent Endpoints for FastAPI
Handles registration, execution, and monitoring of agents via AgentRegistry
Production-ready implementation with simplified and advanced APIs

# orphan:exempt reason: legacy flat file, implementation retained here.
# Routing entry-point migrated to src/core/api/v1/agents/ (SP-API-003 Dag 3).
# Sub-routers in v1/agents/ import helpers and handlers from this module.
# Council gate enforcement lives in v1/agents/ (RC-001, SP-GOV-002 dag 1).
# This legacy file has no direct council gate -- migrate to v1/ to gain it (RC-008).
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency,
    require_scopes,
    OAuth2Scope,
)
from src.core.api.agent_endpoints_db_dependencies import get_db
from src.core.shared.interfaces import AgentCapability, AgentStatus, ExecutionResult, TaskData
from src.core.types import AgentType, TaskPriority

if TYPE_CHECKING:
    from src.core.api.agent_endpoints_dependencies import AgentRegistry
    from src.core.api.agent_endpoints_dependencies import AgentRegistryRepository
    from src.core.api.agent_endpoints_dependencies import RegisteredAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


async def get_agent_registry_dependency(
    session: AsyncSession = Depends(get_db),
) -> "AgentRegistry":
    """Provide a request-scoped AgentRegistry bound to the active DB session."""
    from src.core.api.agent_endpoints_dependencies import AgentRegistry
    from src.core.api.agent_endpoints_dependencies import AgentRegistryRepository

    return AgentRegistry(repository=AgentRegistryRepository(session))


class AgentRegistrationRequest(BaseModel):
    agent_id: str
    address: str
    capabilities: list[str]
    agent_type: str = "specialist"


class AgentRegistrationResponse(BaseModel):
    success: bool
    message: str
    agent_id: str
    id: str


class AgentListResponse(BaseModel):
    agents: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    total_count: int


class SimpleAgentRegistrationRequest(BaseModel):
    name: str
    description: str | None = None
    type: str = "specialist"
    capabilities: list[str] | None = None


class AgentExecutionRequest(BaseModel):
    input: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    priority: TaskPriority = TaskPriority.MEDIUM


class AgentQueryRequest(BaseModel):
    """Schema for agent execution via dispatcher (test support)."""

    agent_id: str
    query: str
    use_rag: bool = False


class RegisteredAPIAgent:
    """Minimal agent implementation capable of executing tasks."""

    def __init__(
        self,
        agent_id: str,
        address: str,
        agent_type: AgentType,
        capabilities: list[AgentCapability],
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.address = address
        self.agent_type = agent_type
        self._capabilities = capabilities
        self.name = name
        self.description = description

    async def get_capabilities(self) -> list[AgentCapability]:
        return self._capabilities

    async def get_status(self) -> AgentStatus:
        """Get current status of this agent (required by Agent protocol)."""
        from datetime import datetime, timezone

        return AgentStatus(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            is_active=True,
            current_load=0.0,
            capabilities=self._capabilities,
            last_heartbeat=datetime.now(timezone.utc),
        )

    async def process_task(self, task: TaskData) -> ExecutionResult:
        logger.info("Agent %s processing task %s", self.agent_id, task.id)
        payload = {
            "agent_id": self.agent_id,
            "address": self.address,
            "task": task.title,
            "input": task.description,
            "metadata": task.metadata,
        }
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data=payload,
            execution_time=0.01,
            logs=["RegisteredAPIAgent processed task"],
        )


class AgentUpdateRequest(BaseModel):
    """Partial update payload for a registered agent."""

    name: str | None = None
    description: str | None = None
    address: str | None = None
    capabilities: list[str] | None = None


class AgentCollaborationRequest(BaseModel):
    """Request payload for lightweight multi-agent collaboration."""

    query: str = Field(..., min_length=1)
    agent_ids: list[str] | None = None


def _parse_agent_type(agent_type: str) -> AgentType:
    try:
        return AgentType(agent_type.lower())
    except ValueError:
        logger.warning("Unknown agent type '%s', defaulting to SPECIALIST", agent_type)
        return AgentType.SPECIALIST


def _build_capabilities(capabilities: list[str]) -> list[AgentCapability]:
    return [
        AgentCapability(
            name=cap,
            description=f"Capability: {cap}",
            input_types=["text"],
            output_types=["text"],
        )
        for cap in capabilities
    ]


async def _perform_registration(
    registry: "AgentRegistry",
    agent_id: str,
    address: str,
    agent_type_value: str,
    capabilities: list[str],
    name: str | None = None,
    description: str | None = None,
) -> AgentRegistrationResponse:
    agent = RegisteredAPIAgent(
        agent_id=agent_id,
        address=address,
        agent_type=_parse_agent_type(agent_type_value),
        capabilities=_build_capabilities(capabilities),
        name=name,
        description=description,
    )

    try:
        success = await registry.register_agent(agent)
        if not success:
            logger.error("agent registration returned False for %s", agent_id)
            raise HTTPException(
                status_code=500,
                detail="Internal error",
            )
    except HTTPException:
        raise
    except AttributeError as e:
        logger.error(
            "agent registry method not available: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=503,
            detail="Agent registration service is currently unavailable",
        )
    except Exception as e:
        logger.error("agent registration failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")

    return AgentRegistrationResponse(
        success=True,
        message=f"Agent {agent_id} registered successfully",
        agent_id=agent_id,
        id=agent_id,
    )


@router.post(
    "/register",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_agent(
    request: AgentRegistrationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> AgentRegistrationResponse:
    """Advanced registration accepting explicit agent identifiers."""
    logger.info(
        "User %s registering agent %s",
        getattr(current_user, "id", None),
        request.agent_id,
    )
    return await _perform_registration(
        registry,
        agent_id=request.agent_id,
        address=request.address,
        agent_type_value=request.agent_type,
        capabilities=request.capabilities,
    )


@router.post("/", response_model=AgentRegistrationResponse, status_code=status.HTTP_201_CREATED)
@router.post(
    "",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/agent/register",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_agent_minimal(
    request: SimpleAgentRegistrationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> AgentRegistrationResponse:
    """Simplified registration backing the unit tests."""
    generated_id = request.name.lower().replace(" ", "_")
    agent_id = f"{generated_id}_{uuid.uuid4().hex[:6]}"
    capabilities = request.capabilities or [f"handle_{request.type}"]
    address = f"agent://{agent_id}"

    return await _perform_registration(
        registry,
        agent_id=agent_id,
        address=address,
        agent_type_value=request.type,
        capabilities=capabilities,
        name=request.name,
        description=request.description,
    )


def _apply_agent_filters(
    agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    category: str | None = None,
    capability: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Apply optional case-insensitive list filters for the agents endpoint."""
    if not isinstance(category, str):
        category = None
    if not isinstance(capability, str):
        capability = None
    if not isinstance(source, str):
        source = None

    filtered = agents

    if category:
        category_normalized = category.strip().lower()
        filtered = [
            agent
            for agent in filtered
            if str(agent.get("category", "")).strip().lower() == category_normalized
        ]

    if capability:
        capability_normalized = capability.strip().lower()
        filtered = [
            agent
            for agent in filtered
            if any(
                str(agent_capability).strip().lower() == capability_normalized
                for agent_capability in agent.get("capabilities", [])
            )
        ]

    if source:
        source_normalized = source.strip().lower()
        filtered = [
            agent
            for agent in filtered
            if str(agent.get("source", "")).strip().lower() == source_normalized
        ]

    return filtered


@router.get("/", response_model=AgentListResponse)
async def list_agents(
    category: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> AgentListResponse:
    """Return all agents: enterprise catalog (YAML) + ActivePieces integrations."""
    logger.info("User %s retrieving all agents", getattr(current_user, "id", None))
    try:
        formatted_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type

        # 1. Enterprise Catalog Agents (primary source -- 336 agents from YAML configs)
        try:
            from src.core.als.agents.loader import EnterpriseCatalogLoader

            loader = EnterpriseCatalogLoader()
            loader.load_all()

            # Department-to-category mapping for frontend display
            dept_category_map: dict[str, str] = {
                # Technical
                "it_security": "Technical",
                "it_infra_cyber_security": "Technical",
                "software_engineering": "Technical",
                "engineering": "Technical",
                "technical_services": "Technical",
                "devops": "Technical",
                "ai_engineering": "Technical",
                "mobile_engineering": "Technical",
                "cloud_engineering": "Technical",
                "data_engineering": "Technical",
                "quality_assurance": "Technical",
                # Core
                "core_platform": "Core",
                # Strategic
                "sales_marketing": "Strategic",
                "strategy_business": "Strategic",
                "strategy_business_development": "Strategic",
                "ecommerce_retail": "Strategic",
                "marketing": "Strategic",
                "zzp_sales": "Strategic",
                "zzp_growth": "Strategic",
                # Creative
                "product_innovation": "Creative",
                "product_design": "Creative",
                "communications_pr": "Creative",
                "zzp_branding": "Creative",
                # Analytical
                "data_ai_governance": "Analytical",
                "research_development": "Analytical",
                "business_analysis": "Analytical",
                # Specialized
                "finance_treasury": "Specialized",
                "operations_supply_chain": "Specialized",
                "legal_compliance": "Specialized",
                "legal_risk_compliance": "Specialized",
                "hr_culture": "Specialized",
                "sustainability_esg": "Specialized",
                "logistics_trade": "Specialized",
                "risk_management": "Specialized",
                "zzp_finance": "Specialized",
                "zzp_legal": "Specialized",
                "zzp_ops": "Specialized",
                "facility_management": "Specialized",
                "pmo_project_management": "Specialized",
                # Support
                "customer_experience": "Support",
                "crisis_management": "Support",
                "specialist_services": "Support",
                # Remaining departments
                "admin_lite": "Specialized",
                "hr_lite": "Specialized",
                "facility_mgmt": "Specialized",
                "infrastructure": "Technical",
                "local_marketing": "Strategic",
                "product": "Creative",
                "internal_communications": "Creative",
            }

            for key, cfg in loader.agents.items():
                # Derive category from department
                dept_normalized = (
                    cfg.department.lower()
                    .replace(" ", "_")
                    .replace("&", "")
                    .replace("__", "_")
                    .strip("_")
                )
                agent_category = dept_category_map.get(dept_normalized, "Core")

                # Combine capabilities from allowed_tools and OODA profile
                ooda = cfg.ooda_profile or {}
                ooda_tools = ooda.get("act", {}).get("tools", [])
                capabilities = list(set(cfg.allowed_tools + ooda_tools))

                # Human-readable name from CamelCase class name
                display_name = cfg.class_name.replace("Agent", "").strip()
                # Insert spaces before capitals: "BackendArchitect" -> "Backend Architect"
                display_name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", display_name)

                formatted_agents.append(
                    {
                        "id": key,
                        "agent_id": key,
                        "name": display_name,
                        "type": cfg.department,
                        "category": agent_category,
                        "status": "online" if cfg.is_active else "offline",
                        "description": cfg.description or f"{display_name} specialist agent",
                        "address": f"catalog://{key}",
                        "capabilities": capabilities,
                        "created_at": "2026-03-16T00:00:00Z",
                        "updated_at": "2026-03-16T00:00:00Z",
                        "last_heartbeat": "2026-03-16T00:00:00Z",
                        "source": "native",
                    }
                )
            logger.info(f"Loaded {len(loader.agents)} enterprise catalog agents")
        except Exception as e:
            logger.error(f"Failed to load enterprise catalog: {e}")
            # Graceful degradation: continue without catalog agents

        # 2. Get ActivePieces Integrations (as Virtual Agents)
        try:
            from src.core.activepieces.service import activepieces_service_voor

            # De catalogus komt via de verbinding van DEZE tenant; zonder verbinding is de lijst
            # leeg en niet die van een algemene client (ADR-040 B3/B4).
            active_pieces = await activepieces_service_voor(
                getattr(current_user, "tenant_id", None)
            )
            # Wrap in timeout to prevent hanging if ActivePieces is unavailable
            pieces = await asyncio.wait_for(
                active_pieces.get_all_pieces(),
                timeout=5.0,  # 5 second timeout for ActivePieces
            )

            # Category mapping from ActivePieces to SanskritiSetu
            category_map = {
                "COMMUNICATION": "Communication",
                "MARKETING": "Marketing",
                "SALES": "CRM",  # CRM often maps to Sales
                "CRM": "CRM",
                "PRODUCTIVITY": "Productivity",
                "DEVELOPER_TOOLS": "Technical",  # Mapping to "Technical" native category
                "ARTIFICIAL_INTELLIGENCE": "AI",
                "DATABASES": "Data",
                "DATA": "Data",
                "ECOMMERCE": "E-commerce",
                "SOCIAL_MEDIA": "Social Media",
                "SUPPORT": "Support",  # Mapping to "Support" native category
                "CUSTOMER_SUPPORT": "Support",
                "BUSINESS_INTELLIGENCE": "Analytical",  # Mapping to "Analytical" native category
            }

            for piece in pieces:
                # Map AP Category
                # AP categories are usually uppercase strings in a list
                agent_category = "Integration"  # Default
                if piece.categories:
                    # Prefer the first known category mapping
                    for cat in piece.categories:
                        mapped = category_map.get(cat.upper())
                        if mapped:
                            agent_category = mapped
                            break

                virtual_agent_id = f"ap_{piece.name}"
                piece_actions = cast(
                    dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                    piece.actions,  # TODO(TYPE): replace Any with concrete type
                )  # TODO(TYPE): replace Any with concrete type
                piece_triggers = cast(
                    dict[str, Any], piece.triggers
                )  # TODO(TYPE): replace Any with concrete type

                formatted_agents.append(
                    {
                        "id": virtual_agent_id,
                        "agent_id": virtual_agent_id,
                        "name": piece.display_name,
                        "category": agent_category,
                        "status": "online",  # ActivePieces pieces are always 'available' if service is up
                        "description": piece.description,
                        "address": f"activepieces://{piece.name}",
                        "capabilities": [f"action:{name}" for name in piece_actions.keys()]
                        + [f"trigger:{name}" for name in piece_triggers.keys()],
                        # Use a stable past date or current time? Using fixed epoch for consistency or current
                        "created_at": "2025-01-01T00:00:00Z",
                        "updated_at": "2025-01-01T00:00:00Z",
                        "last_heartbeat": "2025-01-01T00:00:00Z",  # Dummy heartbeat
                        "source": "activepieces",
                        "logo_url": piece.logo_url,
                        "metadata": {
                            "version": piece.version,
                            "actions_count": len(piece_actions),
                            "triggers_count": len(piece_triggers),
                            "original_categories": piece.categories,
                        },
                    }
                )
            logger.info(f"Merged {len(pieces)} ActivePieces integrations into agent list")

        except TimeoutError:
            # Graceful degradation: ActivePieces timeout, continue with native agents
            logger.warning("ActivePieces timeout - returning native agents only")
        except Exception as e:
            # Graceful degradation: Log error but return native agents
            logger.error(f"Failed to fetch ActivePieces pieces: {e}")
            # Do NOT raise exception, just continue with native agents

        filtered_agents = _apply_agent_filters(
            formatted_agents,
            category=category,
            capability=capability,
            source=source,
        )

        total_count = len(filtered_agents)
        paged_agents = filtered_agents[offset : offset + limit]
        return AgentListResponse(agents=paged_agents, total_count=total_count)
    except AttributeError as e:
        logger.error(f"Registry method not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="Agent registry service is unavailable. Please try again later.",
        )
    except Exception as e:
        logger.exception(f"Failed to retrieve agents: {e}")
        raise HTTPException(status_code=500, detail="Internal error retrieving agents")


@router.get("", include_in_schema=False)
async def list_agents_root(
    category: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> AgentListResponse:
    return await list_agents(category, capability, source, limit, offset, current_user, _, registry)


@router.post("/collaborate")
async def collaborate_agents(
    request: AgentCollaborationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Execute a lightweight collaboration flow across multiple agents.

    This endpoint provides a stable API contract while full Phase 3
    collaboration internals are still being rolled out.
    """
    all_agents = await registry.get_all_agents(current_user.tenant_id)
    if not all_agents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registered agents available for collaboration",
        )

    available_ids = {a.get("agent_id") for a in all_agents if a.get("agent_id")}
    if request.agent_ids:
        selected_ids = [aid for aid in request.agent_ids if aid in available_ids]
    else:
        selected_ids = [cast(str, a.get("agent_id")) for a in all_agents[:2] if a.get("agent_id")]

    if not selected_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid agent_ids provided for collaboration",
        )

    synthesis = f"Collaboration completed for query using agents: {', '.join(selected_ids)}"

    return {
        "success": True,
        "collaboration_id": f"collab_{uuid.uuid4().hex[:8]}",
        "query": request.query,
        "participating_agents": selected_ids,
        "synthesis": synthesis,
        "status": "completed",
        "requested_by": getattr(current_user, "id", None),
    }


@router.get("/stats")
async def get_agent_stats(
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get agent statistics for dashboard

    Returns aggregated metrics about registered agents in the current tenant.

    Security: JWT required, tenant isolated via middleware, RBAC enforced

    Returns: Dict[str, Any] with keys: total_agents, active_agents, inactive_agents, health_status  # TODO(TYPE): replace Any with concrete type
    """
    try:
        # Get all agents for current tenant (auto-filtered by AgentRegistry)
        all_agents = await registry.get_all_agents(current_user.tenant_id)

        total_agents = len(all_agents)
        # Count active agents (those that are healthy/available)
        active_agents = sum(
            1
            for agent in all_agents
            if agent.get("status") == "active" or agent.get("is_available", False)
        )

        return {
            "total_agents": total_agents,
            "active_agents": active_agents,
            "inactive_agents": total_agents - active_agents,
            "health_status": "healthy" if total_agents > 0 else "no_agents",
        }
    except Exception as e:
        logger.exception(f"Failed to get agent stats: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve agent statistics"
        )


@router.post(
    "/execute", response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def execute_agent_dispatcher(
    request: AgentQueryRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Execute an agent by ID provided in the body (Dispatcher Pattern).
    Supports RAG flags and direct query mapping.
    """
    return await execute_agent(
        agent_id=request.agent_id,
        request=AgentExecutionRequest(
            input=request.query,
            metadata={"use_rag": request.use_rag, "tenant_id": current_user.tenant_id},
        ),
        current_user=current_user,
        _=_,
        registry=registry,
    )


@router.post("/agent/execute/{agent_id}")
async def execute_agent(
    agent_id: str,
    request: AgentExecutionRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a specific agent with the provided payload."""
    try:
        logger.info(f"Executing agent {agent_id} for user {getattr(current_user, 'id', None)}")

        agent = await registry.get_agent_by_id(agent_id)
        if agent is None:
            logger.error(f"Agent {agent_id} not found in registry or database")
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        logger.info(f"Found agent {agent_id}: {agent}")

        task = TaskData(
            title=f"execute-{agent_id}",
            description=request.input,
            priority=request.priority,
            metadata={
                **request.metadata,
                "agent_id": agent_id,
                "requested_by": getattr(current_user, "id", None),
            },
        )

        logger.info(f"Created task for agent {agent_id}: {task.title}")

        from src.core.shared.config import get_settings

        timeout_seconds = float(get_settings().agent_execution_timeout)
        result = await asyncio.wait_for(
            registry.distribute_task(task),
            timeout=timeout_seconds,
        )

        logger.info(f"Task result: {result}")

        if result is None:
            logger.error(f"Task execution returned None for agent {agent_id}")
            raise HTTPException(status_code=500, detail="Task execution failed - no result")

        if not result.success:
            error_msg = getattr(result, "error_message", "Unknown error") or "Task execution failed"
            logger.error(f"Task failed for agent {agent_id}: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        logger.info(f"Agent {agent_id} executed successfully")

        return {
            "agent_id": agent_id,
            "result": result.result_data or {},
            "status": "completed",
            "execution_time": result.execution_time,
        }

    except TimeoutError:
        from src.core.shared.config import get_settings

        timeout_seconds = float(get_settings().agent_execution_timeout)
        logger.error(f"Agent {agent_id} timed out after {timeout_seconds} seconds")
        raise HTTPException(
            status_code=504,
            detail=f"Agent execution timed out after {timeout_seconds} seconds",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error executing agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Agent execution error")


@router.post("/execute/{agent_id}", include_in_schema=False)
async def execute_agent_legacy(
    agent_id: str,
    request: AgentExecutionRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Legacy alias for plural route consumers."""
    return await execute_agent(agent_id, request, current_user, _, registry)


@router.get("/health")
async def agent_system_health(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Expose aggregate registry health metrics."""
    try:
        status_payload = await registry.get_system_status()
        return {
            "status": "healthy",
            "system_metrics": status_payload,
            "timestamp": status_payload.get("uptime"),
        }
    except AttributeError as e:
        logger.error(f"Registry health check method not available: {e}")
        raise HTTPException(status_code=503, detail="Health check service unavailable")
    except Exception as e:
        logger.exception(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check error")


@router.get("/health", include_in_schema=False)
async def agent_system_health_legacy(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    return await agent_system_health(current_user, _, registry)


# =============================================================================
# ENTERPRISE CATALOG ENDPOINT
# =============================================================================


class CatalogMetadataResponse(BaseModel):
    version: str
    last_updated: str
    totalAgents: int
    totalPacks: int


class EnterpriseCatalogResponse(BaseModel):
    agents: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    packs: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    metadata: CatalogMetadataResponse


@router.get("/catalog", response_model=EnterpriseCatalogResponse)
async def get_enterprise_catalog(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> EnterpriseCatalogResponse:
    """
    Return the complete enterprise agent catalog from YAML config.

    Includes all 135 agents with full metadata and 80 domain packs.
    Results are loaded from config/agents/*.yaml and config/domain_packs.yaml.
    """
    from src.core.als.agents.loader import EnterpriseCatalogLoader

    try:
        loader = EnterpriseCatalogLoader()
        loader.load_all()

        agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for key, cfg in loader.agents.items():
            tools = cfg.allowed_tools or []
            ooda = cfg.ooda_profile or {}
            ooda_tools = ooda.get("act", {}).get("tools", [])
            capabilities = list(set(tools + ooda_tools))

            agents.append(
                {
                    "id": cfg.agent_id,
                    "name": cfg.name,
                    "description": cfg.description or "",
                    "department": cfg.department,
                    "capabilities": capabilities,
                    "version": getattr(cfg, "version", "1.0.0"),
                    "status": "active" if cfg.is_active else "deprecated",
                    "inputs": [
                        {
                            "name": src,
                            "type": "text",
                            "required": True,
                        }
                        for src in ooda.get("observe", {}).get("data_sources", [])
                    ],
                    "outputs": [
                        {
                            "name": tool,
                            "type": "text",
                        }
                        for tool in ooda_tools
                    ],
                    "metadata": {
                        "technology": cfg.technology,
                        "priority": cfg.priority,
                        "class_name": cfg.class_name,
                        "ooda_model": ooda.get("orient", {}).get("model"),
                        "confidence_threshold": ooda.get("decide", {}).get("confidence_threshold"),
                    },
                }
            )

        packs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pid, pack in loader.packs.items():
            category = pid.split(".")[0] if "." in pid else "general"
            packs.append(
                {
                    "id": pack.pack_id,
                    "name": pack.name,
                    "description": f"{pack.name} workflow pack",
                    "category": category,
                    "agents": [step.agent_id for step in pack.steps],
                    "metadata": {
                        "step_count": len(pack.steps),
                        "modes": list({step.mode for step in pack.steps}),
                        "total_sla_seconds": sum(step.sla_seconds for step in pack.steps),
                    },
                }
            )

        from datetime import datetime, timezone

        metadata = CatalogMetadataResponse(
            version="2.0.0",
            last_updated=datetime.now(timezone.utc).isoformat(),
            totalAgents=len(agents),
            totalPacks=len(packs),
        )

        return EnterpriseCatalogResponse(
            agents=agents,
            packs=packs,
            metadata=metadata,
        )

    except ValueError as e:
        logger.error(f"Catalog integrity error: {e}")
        raise HTTPException(status_code=500, detail="Catalog integrity error")
    except Exception as e:
        logger.exception(f"Failed to load enterprise catalog: {e}")
        raise HTTPException(
            status_code=503,
            detail="Enterprise catalog service temporarily unavailable",
        )


# =============================================================================
# PATH-PARAMETER ROUTES -- Must be AFTER all static /path routes to avoid shadowing
# =============================================================================


@router.get("/{agent_id}")
async def get_agent_details(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return a single agent by agent_id."""
    from src.core.api.agent_endpoints_dependencies import RegisteredAgent

    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not resolved")
    stmt = select(RegisteredAgent).where(
        RegisteredAgent.agent_id == agent_id,
        RegisteredAgent.tenant_id == tenant_id,
    )

    result = await session.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "address": agent.address,
        "capabilities": agent.capabilities or [],
        "tenant_id": agent.tenant_id,
        "last_heartbeat": (agent.last_heartbeat.isoformat() if agent.last_heartbeat else None),
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


@router.patch("/{agent_id}")
async def update_agent_details(
    agent_id: str,
    request: AgentUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Partially update mutable agent fields by agent_id."""
    from src.core.api.agent_endpoints_dependencies import AgentRegistryRepository
    from src.core.api.agent_endpoints_dependencies import RegisteredAgent

    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not resolved")
    stmt = select(RegisteredAgent).where(
        RegisteredAgent.agent_id == agent_id,
        RegisteredAgent.tenant_id == tenant_id,
    )

    result = await session.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    updates = request.model_dump(exclude_none=True)
    if "capabilities" in updates:
        updates["capabilities"] = {cap: f"Capability: {cap}" for cap in updates["capabilities"]}

    repo = AgentRegistryRepository(session)
    await repo.update_agent(agent_id, tenant_id, updates)
    await session.refresh(agent)

    return {
        "success": True,
        "message": f"Agent {agent_id} updated successfully",
        "agent": {
            "id": agent.id,
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "address": agent.address,
            "capabilities": (
                list((agent.capabilities or {}).keys())
                if isinstance(agent.capabilities, dict)
                else (agent.capabilities or [])
            ),
            "tenant_id": agent.tenant_id,
        },
    }
