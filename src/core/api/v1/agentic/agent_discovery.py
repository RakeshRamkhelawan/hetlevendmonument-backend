"""Phase 0a: Agent Discovery API Endpoints
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

Implements agent discovery endpoints with department and function filtering.
These endpoints expose the department and function metadata synchronized in Task #5
to enable intelligent agent routing and selection based on organizational structure.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.agentic.dependencies import AgentRegistry, AgentRegistryRepository, get_db
from src.core.auth.api_deps import get_current_user_dependency as get_current_user
from src.core.middleware.tenant_context import require_tenant_id

# =============================================================================
# Models for Discovery API
# =============================================================================


class DepartmentInfo(BaseModel):
    """Department information for discovery."""

    name: str = Field(..., description="Department name")
    value: str = Field(..., description="Department enum value")
    description: str = Field(..., description="Department description")
    agent_count: int = Field(default=0, description="Number of agents in department")


class FunctionCapability(BaseModel):
    """Function/capability information."""

    name: str = Field(..., description="Function/capability name")
    description: str = Field(..., description="What this function does")
    agent_count: int = Field(default=0, description="Number of agents with this function")


class AgentDiscoveryItem(BaseModel):
    """Agent information for discovery endpoints."""

    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent display name")
    department: str | None = Field(None, description="Department assignment")
    functions: list[str] = Field(default_factory=list, description="Function/capability tags")
    description: str = Field(default="", description="Agent description")
    status: str = Field(default="active", description="Agent status (active, inactive, etc.)")


class DepartmentAgentsResponse(BaseModel):
    """Response for agents grouped by department."""

    department: str = Field(..., description="Department name")
    agents: list[AgentDiscoveryItem] = Field(
        default_factory=list, description="Agents in department"
    )
    total: int = Field(default=0, description="Total number of agents in department")
    limit: int = Field(default=50, description="Limit for this page")
    offset: int = Field(default=0, description="Offset for this page")


class FunctionAgentsResponse(BaseModel):
    """Response for agents grouped by function."""

    function: str = Field(..., description="Function name")
    agents: list[AgentDiscoveryItem] = Field(
        default_factory=list, description="Agents with function"
    )
    total: int = Field(default=0, description="Total number of agents with function")
    limit: int = Field(default=50, description="Limit for this page")
    offset: int = Field(default=0, description="Offset for this page")


class AgentDiscoveryResponse(BaseModel):
    """Response for agent discovery queries."""

    agents: list[AgentDiscoveryItem] = Field(default_factory=list, description="Matching agents")
    total: int = Field(default=0, description="Total count")
    limit: int = Field(default=50, description="Limit for this page")
    offset: int = Field(default=0, description="Offset for this page")
    filtered_by_department: str | None = Field(None, description="If filtered by department")
    filtered_by_function: str | None = Field(None, description="If filtered by function")


# =============================================================================
# Router Setup
# =============================================================================


router = APIRouter(
    prefix="/discovery",
    tags=["Agent Discovery"],
    dependencies=[Depends(get_current_user)],
)


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_all_agents(tenant_id: int, session: AsyncSession) -> list[AgentDiscoveryItem]:
    """Get tenant-scoped agents from the registry with department and function metadata."""
    registry = AgentRegistry(repository=AgentRegistryRepository(session))
    discovery_agents = await registry.get_discovery_agents(tenant_id)
    return [AgentDiscoveryItem(**a) for a in discovery_agents]


async def _get_all_departments(tenant_id: int, session: AsyncSession) -> list[DepartmentInfo]:
    """Get all available departments with agent counts."""
    agents = await _get_all_agents(tenant_id, session)

    department_map = {
        "DATA_AI_GOVERNANCE": "Data & AI Governance",
        "OPERATIONS": "Operations",
        "CUSTOMER_EXPERIENCE": "Customer Experience",
        "SALES_MARKETING": "Sales & Marketing",
        "IT_SECURITY": "IT Security",
        "LEGAL_COMPLIANCE": "Legal & Compliance",
        "HR": "Human Resources",
        "FINANCE": "Finance",
        "PRODUCT_INNOVATION": "Product & Innovation",
        "STRATEGY": "Strategy",
    }

    departments = []
    for dept_value, dept_name in department_map.items():
        count = sum(1 for agent in agents if agent.department == dept_value)
        departments.append(
            DepartmentInfo(
                name=dept_name,
                value=dept_value,
                description=f"Agents in {dept_name} department",
                agent_count=count,
            )
        )

    return departments


async def _get_all_functions(tenant_id: int, session: AsyncSession) -> list[FunctionCapability]:
    """Get all available functions with agent counts."""
    agents = await _get_all_agents(tenant_id, session)

    # Collect all unique functions
    all_functions: dict[str, int] = {}
    for agent in agents:
        for func in agent.functions:
            if func not in all_functions:
                all_functions[func] = 0
            all_functions[func] += 1

    functions = [
        FunctionCapability(
            name=func,
            description=f"Agents with {func} capability",
            agent_count=count,
        )
        for func, count in sorted(all_functions.items())
    ]

    return functions


# =============================================================================
# Discovery Endpoints
# =============================================================================


@router.get("/departments", response_model=list[DepartmentInfo])
async def list_all_departments(
    db: AsyncSession = Depends(get_db),
) -> list[DepartmentInfo]:
    """
    Discover all available departments and their agent counts.

    Returns a list of departments with the number of agents in each.
    This enables UI components to present department-based navigation.

    Responses:
    - 200: List[DepartmentInfo] - all departments with agent counts
    """
    logger.info("list_all_departments requested")
    tenant_id = require_tenant_id()
    return await _get_all_departments(tenant_id, db)


@router.get("/functions", response_model=list[FunctionCapability])
async def list_all_functions(
    db: AsyncSession = Depends(get_db),
) -> list[FunctionCapability]:
    """
    Discover all available functions and their agent counts.

    Returns a list of capabilities/functions with the number of agents
    that support each. This enables capability-based agent selection.

    Responses:
    - 200: List[FunctionCapability] - all functions with agent counts
    """
    logger.info("list_all_functions requested")
    tenant_id = require_tenant_id()
    return await _get_all_functions(tenant_id, db)


@router.get("", response_model=AgentDiscoveryResponse)
async def discover_agents(
    department: str | None = Query(None, description="Filter by department name"),
    function: str | None = Query(None, description="Filter by function/capability"),
    status: str | None = Query(None, description="Filter by status (active, inactive, etc.)"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
) -> AgentDiscoveryResponse:
    """
    Discover agents with optional filtering by department, function, or status.

    Query Parameters:
    - department: Filter by department (e.g., "FINANCE", "OPERATIONS")
    - function: Filter by function/capability (e.g., "ai-engineering", "security")
    - status: Filter by status (e.g., "active", "inactive")
    - limit: Maximum results (default: 50, max: 1000)
    - offset: Results to skip for pagination (default: 0)

    Returns agents matching the filters with pagination support.

    Responses:
    - 200: AgentDiscoveryResponse with agents paginated
    - 400: Invalid filter values
    """
    logger.info(
        "discover_agents requested",
        department=department,
        function=function,
        status=status,
        limit=limit,
        offset=offset,
    )

    tenant_id = require_tenant_id()
    agents = await _get_all_agents(tenant_id, db)

    # Apply filters
    filtered = agents

    if status:
        filtered = [a for a in filtered if a.status == status]

    if department:
        filtered = [a for a in filtered if a.department == department]

    if function:
        filtered = [a for a in filtered if function in a.functions]

    # Apply pagination
    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return AgentDiscoveryResponse(
        agents=paginated,
        total=total,
        limit=limit,
        offset=offset,
        filtered_by_department=department,
        filtered_by_function=function,
    )


@router.get(
    "/by-department/{department}",
    response_model=DepartmentAgentsResponse,
)
async def get_agents_by_department(
    department: str = Path(..., description="Department name"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
) -> DepartmentAgentsResponse:
    """
    Get all agents in a specific department.

    Path Parameters:
    - department: Department enum value (e.g., "FINANCE", "OPERATIONS", "DATA_AI_GOVERNANCE")

    Returns all agents assigned to the specified department with pagination.

    Responses:
    - 200: DepartmentAgentsResponse with agents paginated
    - 400: Invalid department value
    - 404: Department not found
    """
    logger.info(
        "get_agents_by_department requested",
        department=department,
        limit=limit,
        offset=offset,
    )

    tenant_id = require_tenant_id()
    agents = await _get_all_agents(tenant_id, db)

    # Filter by department
    dept_agents = [a for a in agents if a.department == department]

    if not dept_agents:
        logger.warning(
            "department_not_found",
            department=department,
        )
        raise HTTPException(
            status_code=404,
            detail="Department not found",
        )

    # Apply pagination
    total = len(dept_agents)
    paginated = dept_agents[offset : offset + limit]

    return DepartmentAgentsResponse(
        department=department,
        agents=paginated,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/by-function/{function}",
    response_model=FunctionAgentsResponse,
)
async def get_agents_by_function(
    function: str = Path(..., description="Function/capability name"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
) -> FunctionAgentsResponse:
    """
    Get all agents with a specific function or capability.

    Path Parameters:
    - function: Function name (e.g., "ai-engineering", "security", "deployment")

    Returns all agents that support the specified function with pagination.

    Responses:
    - 200: FunctionAgentsResponse with agents paginated
    - 400: Invalid function value
    - 404: Function not found
    """
    logger.info(
        "get_agents_by_function requested",
        function=function,
        limit=limit,
        offset=offset,
    )

    tenant_id = require_tenant_id()
    agents = await _get_all_agents(tenant_id, db)

    # Filter by function
    func_agents = [a for a in agents if function in a.functions]

    if not func_agents:
        logger.warning(
            "function_not_found",
            function=function,
        )
        raise HTTPException(
            status_code=404,
            detail="Function not found",
        )

    # Apply pagination
    total = len(func_agents)
    paginated = func_agents[offset : offset + limit]

    return FunctionAgentsResponse(
        function=function,
        agents=paginated,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/agent/{agent_id}", response_model=AgentDiscoveryItem)
async def get_agent_details(
    agent_id: str = Path(..., description="Agent ID"),
    db: AsyncSession = Depends(get_db),
) -> AgentDiscoveryItem:
    """
    Get detailed information about a specific agent.

    Path Parameters:
    - agent_id: Agent identifier (e.g., "ai-engineer", "cloud-architect")

    Returns complete agent information including department and functions.

    Responses:
    - 200: AgentDiscoveryItem with full agent details
    - 404: Agent not found
    """
    logger.info(
        "get_agent_details requested",
        agent_id=agent_id,
    )

    tenant_id = require_tenant_id()
    agents = await _get_all_agents(tenant_id, db)

    agent = next((a for a in agents if a.agent_id == agent_id), None)

    if not agent:
        logger.warning(
            "agent_not_found",
            agent_id=agent_id,
        )
        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    return agent
