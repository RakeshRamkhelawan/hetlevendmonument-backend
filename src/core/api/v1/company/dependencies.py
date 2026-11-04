# ADR-033 facade: re-exports voor pack_feedback_endpoints.py proxy stub.
# TODO(SP-API-011): GlobalPack + PackFeedback naar src.domains.packs.models verplaatsen.
from uuid import UUID

from sqlalchemy import select

from src.core.api.auth.dependencies import validate_csrf_token as validate_csrf_token
from src.core.auth.dependencies import (
    controleer_resource_recht as controleer_resource_recht,
    require_resource_permission as require_resource_permission,
)
from src.core.company.board_service import (
    BoardRoleError as BoardRoleError,
    BoardService as BoardService,
    BoardServiceError as BoardServiceError,
    GoldenRuleR3Violation as GoldenRuleR3Violation,
)
from src.core.copilot.council.metrics import COUNCIL_TURNS_TOTAL as COUNCIL_TURNS_TOTAL
from src.core.database.database import DatabaseManager as DatabaseManager, get_db as get_db
from src.core.governance.audit import audit_service as audit_service
from src.core.governance.models import GlobalPack as GlobalPack, PackFeedback as PackFeedback
from src.core.governance.policy_engine import PolicyEngine as PolicyEngine
from src.core.services.experiment_service import ExperimentService as ExperimentService

__all__ = [
    "BoardRoleError",
    "BoardService",
    "BoardServiceError",
    "COUNCIL_TURNS_TOTAL",
    "DatabaseManager",
    "ExperimentService",
    "get_db",
    "GlobalPack",
    "GoldenRuleR3Violation",
    "PackFeedback",
    "PolicyEngine",
    "audit_service",
    "controleer_resource_recht",
    "get_external_agent_tenant_id",
    "require_resource_permission",
    "validate_csrf_token",
]


async def get_external_agent_tenant_id(db_manager: DatabaseManager, agent_id: UUID) -> int | None:
    """Resolve tenant_id for an external agent via DB lookup (no JWT).

    Used by API-key authenticated endpoints. Returns None if the agent
    does not exist -- callers must treat that as 401, not leak agent
    existence via a different status code.
    """
    from src.core.company.models import ExternalAgent

    async with db_manager.get_session() as session:
        result = await session.execute(select(ExternalAgent).where(ExternalAgent.id == agent_id))
        found_agent = result.scalar_one_or_none()

    return found_agent.tenant_id if found_agent is not None else None
