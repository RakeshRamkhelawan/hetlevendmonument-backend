"""Agent management API endpoints."""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.core.api.v1.agentic import agency_capabilities
from src.core.api.v1.agentic.dependencies import AgentCatalogLoader, AgentConfig
from src.core.auth.api_deps import get_current_user
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


# Models
class AgentListItem(BaseModel):
    id: str
    name: str
    supervisor: str
    domain: str
    status: str


class OodaProfile(BaseModel):
    """OODA profile for an agent."""

    observe: dict[str, object]
    orient: dict[str, object]
    decide: dict[str, object]
    act: dict[str, object]


class DecisionBoundaries(BaseModel):
    """Decision boundaries for an agent."""

    can: list[str]
    cannot: list[str]
    must_escalate: list[str]


class AgentDetail(BaseModel):
    id: str
    name: str
    supervisor: str
    domain: str
    role: str
    responsibility: str
    version: str
    status: str
    ooda_profile: OodaProfile
    decision_boundaries: DecisionBoundaries


class AgentCreateRequest(BaseModel):
    id: str
    name: str
    supervisor: str
    domain: str
    role: str
    responsibility: str
    ooda_profile: OodaProfile | None = None
    decision_boundaries: DecisionBoundaries | None = None


class AgentValidationResponse(BaseModel):
    valid: bool
    errors: list[str]


class AgentLoadResponse(BaseModel):
    loaded: int
    failed: int
    agents: list[str]


class AgentUploadResponse(BaseModel):
    uploaded: bool
    filename: str
    agent_id: str
    message: str


class AgentOodaProfileResponse(BaseModel):
    agent_id: str
    ooda_profile: OodaProfile


class AgentDecisionBoundariesResponse(BaseModel):
    agent_id: str
    decision_boundaries: DecisionBoundaries


class AgentReloadResponse(BaseModel):
    agent_id: str
    reloaded: bool
    timestamp: str


class AgentDeleteResponse(BaseModel):
    agent_id: str
    deleted: bool
    message: str


# Endpoints
@router.get("", response_model=list[AgentListItem])
async def list_agents(
    supervisor: str | None = None, domain: str | None = None, status: str | None = None
) -> list[AgentListItem]:
    """List all agents with optional filtering."""
    # Placeholder - would query from database/registry
    agents = [
        AgentListItem(
            id="finance.tax_compliance.001",
            name="Tax Compliance Agent",
            supervisor="finance.treasury.supervisor",
            domain="Finance & Treasury",
            status="active",
        ),
        AgentListItem(
            id="finance.audit_compliance.001",
            name="Audit Compliance Agent",
            supervisor="finance.treasury.supervisor",
            domain="Finance & Treasury",
            status="active",
        ),
        AgentListItem(
            id="hr.talent_acquisition.001",
            name="Talent Acquisition Agent",
            supervisor="hr.culture.supervisor",
            domain="HR & Culture",
            status="active",
        ),
    ]

    # Apply filters
    if supervisor:
        agents = [a for a in agents if a.supervisor == supervisor]
    if domain:
        agents = [a for a in agents if a.domain == domain]
    if status:
        agents = [a for a in agents if a.status == status]

    return agents


@router.post("/validate", response_model=AgentValidationResponse)
async def validate_agent_config(config: AgentCreateRequest) -> AgentValidationResponse:
    """Validate an agent configuration without saving."""
    errors: list[str] = []
    # Validate required fields
    if not config.id:
        errors.append("Agent ID is required")
    if not config.name:
        errors.append("Agent name is required")
    if not config.supervisor:
        errors.append("Supervisor is required")

    # Validate ID format
    if config.id and not all(c.isalnum() or c in "._-" for c in config.id):
        errors.append("Agent ID contains invalid characters")

    return AgentValidationResponse(valid=len(errors) == 0, errors=errors)


@router.post("/load", response_model=AgentLoadResponse)
async def load_agents_from_directory(
    directory: str = "config/agents", tenant_id: str | None = None
) -> AgentLoadResponse:
    """Load agents from YAML files in a directory."""
    try:
        loader = AgentCatalogLoader()
        base_dir = Path(__file__).resolve().parents[5] / "config/agents"
        requested = Path(directory).resolve()
        try:
            requested.relative_to(base_dir)
        except ValueError as ve:
            raise HTTPException(
                status_code=400, detail="Directory must be under config/agents"
            ) from ve

        if not requested.exists():
            raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

        agents = loader.load_from_directory(requested)  # type: ignore[attr-defined]

        tenant_label = f" for tenant {tenant_id}" if tenant_id else ""
        logger.info("Loaded %d agents from %s%s", len(agents), directory, tenant_label)
        return AgentLoadResponse(
            loaded=len(agents),
            failed=0,  # Would track actual failures
            agents=[a.id for a in agents],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("agent load failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/upload", response_model=AgentUploadResponse)
async def upload_agent_yaml(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> AgentUploadResponse:
    """Upload and register a new agent from YAML file."""
    if file.filename is None or not file.filename.endswith((".yaml", ".yml")):
        raise HTTPException(status_code=400, detail="File must be YAML format")

    # NOTE: content_type is client-controlled; the filename extension check below
    # is the actual trust boundary. Once YAML parsing is implemented, validate
    # the parsed structure rather than relying solely on the declared MIME type.
    if file.content_type is not None and file.content_type not in (
        "application/x-yaml",
        "text/yaml",
        "text/plain",
    ):
        raise HTTPException(status_code=400, detail="Invalid content type")

    MAX_UPLOAD_BYTES = 1024 * 1024  # 1 MiB
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds 1 MiB size limit")

    try:
        # Would parse and validate YAML here
        _ = content.decode("utf-8")

        return AgentUploadResponse(
            uploaded=True,
            filename=file.filename,
            agent_id="parsed_agent_id",  # Would extract from YAML
            message=f"Agent uploaded successfully for tenant {current_user.tenant_id}",
        )

    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8") from e


# Keep agency capability endpoints under /api/v1/agentic/agents/*.
# Included AFTER static routes to prevent subrouter paths from shadowing
# /validate, /load, /upload and similar fixed endpoints.
router.include_router(agency_capabilities.router)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(agent_id: str) -> AgentDetail:
    """Get detailed information about a specific agent."""
    # Placeholder - would load from YAML/database
    if "tax" in agent_id:
        return AgentDetail(
            id=agent_id,
            name="Tax Compliance Agent",
            supervisor="finance.treasury.supervisor",
            domain="Finance & Treasury",
            role="Tax Specialist",
            responsibility="Handle tax calculations and filings",
            version="1.0.0",
            status="active",
            ooda_profile=OodaProfile(
                observe={"data_sources": ["tax_db", "regulations"]},
                orient={"models": ["tax_calculation"]},
                decide={"type": "deterministic", "confidence_threshold": 0.95},
                act={"tools": ["calculator", "filing_system"], "human_approval": False},
            ),
            decision_boundaries=DecisionBoundaries(
                can=["calculate_tax", "file_return"],
                cannot=["change_rates"],
                must_escalate=["audit", "dispute"],
            ),
        )

    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/{agent_id}/ooda", response_model=AgentOodaProfileResponse)
async def get_agent_ooda_profile(
    agent_id: str,
) -> AgentOodaProfileResponse:
    """Get OODA profile for an agent."""
    # Placeholder
    return AgentOodaProfileResponse(
        agent_id=agent_id,
        ooda_profile=OodaProfile(
            observe={"data_sources": ["api", "database"]},
            orient={"models": ["default"]},
            decide={"type": "deterministic", "confidence_threshold": 0.9},
            act={"tools": ["tool_1", "tool_2"], "human_approval": False},
        ),
    )


@router.get("/{agent_id}/decisions", response_model=AgentDecisionBoundariesResponse)
async def get_agent_decision_boundaries(
    agent_id: str,
) -> AgentDecisionBoundariesResponse:
    """Get decision boundaries for an agent."""
    # Placeholder
    return AgentDecisionBoundariesResponse(
        agent_id=agent_id,
        decision_boundaries=DecisionBoundaries(
            can=["task_1", "task_2"],
            cannot=["restricted_task"],
            must_escalate=["critical_task"],
        ),
    )


@router.post("/{agent_id}/reload", response_model=AgentReloadResponse)
async def reload_agent(
    agent_id: str,
) -> AgentReloadResponse:
    """Reload an agent configuration from YAML."""
    # Placeholder - would reload from disk
    return AgentReloadResponse(agent_id=agent_id, reloaded=True, timestamp="2026-02-28T10:00:00Z")


@router.delete("/{agent_id}", response_model=AgentDeleteResponse)
async def delete_agent(
    agent_id: str,
) -> AgentDeleteResponse:
    """Deactivate/delete an agent."""
    # Placeholder - would mark as inactive in database
    return AgentDeleteResponse(
        agent_id=agent_id,
        deleted=True,
        message=f"Agent {agent_id} has been deactivated",
    )
