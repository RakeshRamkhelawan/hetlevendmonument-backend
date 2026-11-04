"""Gedeelde dependencies voor het `hr`-domein -- hergebruikt bestaande, niet opnieuw gebouwd.

`_resolve_tenant_id` (niet `Depends(require_tenant_id)` los) is bewust hetzelfde patroon als
`admin/users_router.py`: dat geeft in tests een `TESTING=1`-uitwijkpad via `current_user.
tenant_id` i.p.v. een aparte dependency-override voor de tenant-context nodig te hebben.

`hr_import_read_limit`/`hr_import_write_limit`/`AuditService` staan hier en NIET direct in de
`*_router.py`-bestanden: ADR-033 par. 2 verbiedt `router.py` om `governance` rechtstreeks te
importeren. Vier architecture-guards (`test_dsm002_dag6_zero_violations.py`,
`test_dsm_api_violations.py`, `test_importlinter_contract1_covers_sub_routers.py`,
`test_sp_api_010_backlog.py`) vingen dit exact toen de routers deze aanvankelijk rechtstreeks
importeerden -- bevestigt dat die guards echt iets meten, niet holle checks zijn.

`get_hr_skills_import_repository`/`get_hr_trainings_import_repository`: de routers importeren
de klassen nog wel (nodig voor het `Depends()`-return-type), maar CONSTRUEREN ze niet meer
zelf -- dat was een Gate 2-bevinding (code-review BE-AGT-060 dag 3, finding 4): een router die
zelf `HRSkillsImportRepository(db)` opbouwt en daarna direct `db.commit()` aanroept, is precies
het Laag 1-patroon dat ADR-033's beslissingstekst als violation noemt ("rechtstreeks te praten
met repositories"). De router behoudt wel zijn EIGEN `db: AsyncSession = Depends(get_db)`
-- nodig voor de eigen `commit()`/`rollback()` -- FastAPI's dependency-cache zorgt dat dat
dezelfde sessie is als die de repository via deze provider kreeg (beide resolven via hetzelfde
`Depends(get_db)`-object binnen een verzoek).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.admin.dependencies import (
    UserResponse,
    _resolve_tenant_id,
    get_current_user,
    require_resource_permission,
)
from src.core.database.database import get_db
from src.core.governance.rate_limiter import hr_import_read_limit, hr_import_write_limit
from src.core.governance.four_eyes import is_four_eyes_required
from src.core.governance.services.audit_service import AuditService
from src.core.repositories.hr_skills_import_repository import HRSkillsImportRepository
from src.core.repositories.hr_deadlines_repository import (
    AnalysisBeforeStart,
    DeadlineInput,
    HRDeadlinesRepository,
    UnknownEmployee,
    UpcomingItem,
)
from src.core.repositories.hr_training_proposals_repository import (
    HRTrainingProposalsRepository,
    ProposalInputNotFound,
    build_explanation,
)
from src.core.repositories.hr_trainings_repository import HRTrainingsRepository
from src.core.tool_broker.hr_registry import GAP_TOOL_NAME, SCHEDULE_TOOL_NAME, HRToolRegistry


def _vereis_hr_recht(actie: str) -> Callable[..., Awaitable[UserResponse]]:
    """Het recht `hr:<actie>` uit de database (rol `hr_medewerker`; de beheerder via `*:*`).

    Tot de HR-pilot (2026-10-10) vroeg elke HR-route een beheerdersrol; een medewerker van
    personeelszaken kon dus niet importeren. De gebruiker komt terug zodat de route de tenant
    uit de JWT-context kan halen (ADR-003), nooit uit het verzoek.
    """
    toets = require_resource_permission("hr", actie)

    async def _afhankelijkheid(
        current_user: UserResponse = Depends(get_current_user),
        _user_id: int = Depends(toets),
    ) -> UserResponse:
        return current_user

    return _afhankelijkheid


require_hr_read = _vereis_hr_recht("read")
require_hr_write = _vereis_hr_recht("write")
require_hr_approve = _vereis_hr_recht("approve")


#: (tenant_id, limit, offset) -> hetzelfde antwoord dat de agent van `analyze_skill_gap` krijgt.
HRGapReader = Callable[[int, int, int], Awaitable[dict[str, object]]]


def get_hr_gap_reader(db: AsyncSession = Depends(get_db)) -> HRGapReader:
    """De kloofanalyse voor het scherm: DEZELFDE query als de agent-tool, dus dezelfde cijfers.

    De registry krijgt de sessie van dit verzoek (en dus de tenantcontext en transactie ervan)
    in plaats van een eigen sessie; zo ziet een leesverzoek wat de import net schreef.
    """

    @asynccontextmanager
    async def _deze_sessie() -> AsyncIterator[AsyncSession]:
        yield db

    registry = HRToolRegistry(session_factory=_deze_sessie)

    async def _lees(tenant_id: int, limit: int, offset: int) -> dict[str, object]:
        return await registry.execute_hr_tool(
            GAP_TOOL_NAME, {"limit": limit, "offset": offset}, tenant_id=tenant_id
        )

    return _lees


#: (e-mailadres, trainingsnaam) -> antwoord van `schedule_training`. Het BESTAANDE pad: dezelfde
#: registry en dezelfde schrijfmethode als de agent-tool, dus geen tweede schrijfweg naar
#: `employee_trainings`. Let op: die methode commit de sessie van dit verzoek bij succes.
HRTrainingScheduler = Callable[[int, str, str], Awaitable[dict[str, object]]]


def get_hr_training_scheduler(db: AsyncSession = Depends(get_db)) -> HRTrainingScheduler:
    @asynccontextmanager
    async def _deze_sessie() -> AsyncIterator[AsyncSession]:
        yield db

    registry = HRToolRegistry(session_factory=_deze_sessie)

    async def _wijs_toe(tenant_id: int, user_email: str, training_name: str) -> dict[str, object]:
        return await registry.execute_hr_tool(
            SCHEDULE_TOOL_NAME,
            {"user_email": user_email, "training_name": training_name},
            tenant_id=tenant_id,
        )

    return _wijs_toe


def get_hr_deadlines_repository(db: AsyncSession = Depends(get_db)) -> HRDeadlinesRepository:
    return HRDeadlinesRepository(db)


def get_hr_training_proposals_repository(
    db: AsyncSession = Depends(get_db),
) -> HRTrainingProposalsRepository:
    return HRTrainingProposalsRepository(db)


def get_hr_skills_import_repository(
    db: AsyncSession = Depends(get_db),
) -> HRSkillsImportRepository:
    return HRSkillsImportRepository(db)


def get_hr_trainings_import_repository(
    db: AsyncSession = Depends(get_db),
) -> HRTrainingsRepository:
    return HRTrainingsRepository(db)


__all__ = [
    "AuditService",
    "UserResponse",
    "HRSkillsImportRepository",
    "HRTrainingsRepository",
    "_resolve_tenant_id",
    "get_db",
    "AnalysisBeforeStart",
    "DeadlineInput",
    "HRDeadlinesRepository",
    "HRGapReader",
    "UnknownEmployee",
    "UpcomingItem",
    "get_hr_deadlines_repository",
    "HRTrainingProposalsRepository",
    "HRTrainingScheduler",
    "ProposalInputNotFound",
    "build_explanation",
    "get_current_user",
    "get_hr_training_proposals_repository",
    "get_hr_training_scheduler",
    "is_four_eyes_required",
    "require_hr_approve",
    "get_hr_gap_reader",
    "get_hr_skills_import_repository",
    "get_hr_trainings_import_repository",
    "hr_import_read_limit",
    "hr_import_write_limit",
    "require_hr_read",
    "require_hr_write",
]
