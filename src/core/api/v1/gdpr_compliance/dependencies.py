"""GDPR Compliance domain dependencies (ADR-033).

Shared dependencies for all gdpr_compliance sub-routers.
Imports of src.core.database / src.core.agents / src.core.governance /
src.core.workflow zijn hier toegestaan (niet in router-bestanden).
"""

from src.core.agents.models import Agent  # noqa: F401
from src.core.api.v1.admin.dependencies import require_admin_role
from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user
from src.core.database.database import get_db
from src.core.governance.dependencies import (
    LawfulBasisMissingError as LawfulBasisMissingError,
    LawfulBasisRegistry as LawfulBasisRegistry,
    get_lawful_basis_registry as get_lawful_basis_registry,
)
from src.core.governance.audit import AuditService as AuditService  # noqa: F401
from src.core.governance.audit import audit_rows_about_user as audit_rows_about_user  # noqa: F401
from src.core.governance.models import AIDecision as AIDecision  # noqa: F401
from src.core.governance.models import AuditLog  # noqa: F401
from src.core.middleware.tenant_context import get_tenant_id as get_current_tenant_id
from src.core.workflow.models import C7ExecutionTask, C7Workflow  # noqa: F401
from fastapi import Depends, HTTPException
from src.core.api.v1.users.shared import (
    can_manage_users,
    eis_dat_gebruiker_uitgeschakeld_mag_worden as eis_dat_gebruiker_uitgeschakeld_mag_worden,
    eis_dat_tenant_gewist_mag_worden as eis_dat_tenant_gewist_mag_worden,
)
from src.core.governance.avg_auditlog import (  # noqa: F401
    anonimiseer_auditlog_van_tenant as anonimiseer_auditlog_van_tenant,
    anonimiseer_bewaarde_rapporten_van_tenant as anonimiseer_bewaarde_rapporten_van_tenant,
    ruim_tenant_blokkades_op as ruim_tenant_blokkades_op,
)
from src.core.governance.avg_tenant_export import (  # noqa: F401
    ACTIE_AANGEBODEN as ACTIE_AANGEBODEN,
    bouw_tenant_dossier as bouw_tenant_dossier,
    dossier_checksum as dossier_checksum,
    export_aangeboden as export_aangeboden,
    export_is_te_vaak_gevraagd as export_is_te_vaak_gevraagd,
    telling as telling,
)
from src.core.governance.avg_wissing_planning import (  # noqa: F401
    activeer_tenant as activeer_tenant,
    eigen_gebruiker as eigen_gebruiker,
    gebruikers_met_geplande_wissing as gebruikers_met_geplande_wissing,
    meld_tenant_zonder_beheerder as meld_tenant_zonder_beheerder,
    is_door_aanvraag_inactief as is_door_aanvraag_inactief,
    lopende_delete_all as lopende_delete_all,
    plan_gebruiker_wissing as plan_gebruiker_wissing,
    termijn_is_verstreken as termijn_is_verstreken,
    trek_gebruiker_wissing_in as trek_gebruiker_wissing_in,
)
from src.core.shared.tenant_beheerders import is_laatste_beheerder as is_laatste_beheerder


async def require_user_manager_eigen_tenant(
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
) -> UserResponse:
    """Mag deze gebruiker gebruikers beheren in de EIGEN tenant? De tenant komt uit de JWT.

    Anders dan `require_user_manager` (src/core/api/v1/users/shared.py) neemt deze GEEN tenant uit
    een queryparameter: een wissing mag nooit over een door de aanvrager opgegeven tenant gaan.
    """
    if tenant_id is None or not can_manage_users(current_user, tenant_id):
        raise HTTPException(status_code=403, detail="Gebruikersbeheer vereist beheerdersrechten")
    return current_user


def standaard_bewaartermijnen_dagen() -> tuple[int, int]:
    """(persoonsgegevens, auditlog) in dagen, uit de EU-standaardtabel van de opruimtaak.

    Een bron voor de AVG-statuspagina: tot 2026-10-14 stond daar een vast getal (90) dat met geen
    enkele termijn in `retention_cleanup.DEFAULT_POLICIES` overeenkwam. De opruimtaak draait de
    EU-termijnen voor elke tenant; een keuze per tenant bestaat in de code niet (niet verder
    gemeten dan `retention_cleanup_job.py`).
    """
    from src.core.governance.retention_cleanup import (
        DataCategory,
        RetentionJurisdiction,
        get_default_policy,
    )

    persoon = get_default_policy(RetentionJurisdiction.EU, DataCategory.PERSONAL_DATA)
    audit = get_default_policy(RetentionJurisdiction.EU, DataCategory.AUDIT_LOG)
    return persoon.retention_days, audit.retention_days


__all__ = [
    "standaard_bewaartermijnen_dagen",
    "ACTIE_AANGEBODEN",
    "bouw_tenant_dossier",
    "dossier_checksum",
    "export_aangeboden",
    "export_is_te_vaak_gevraagd",
    "telling",
    "anonimiseer_auditlog_van_tenant",
    "anonimiseer_bewaarde_rapporten_van_tenant",
    "ruim_tenant_blokkades_op",
    "activeer_tenant",
    "eigen_gebruiker",
    "gebruikers_met_geplande_wissing",
    "is_door_aanvraag_inactief",
    "is_laatste_beheerder",
    "lopende_delete_all",
    "meld_tenant_zonder_beheerder",
    "plan_gebruiker_wissing",
    "require_user_manager_eigen_tenant",
    "termijn_is_verstreken",
    "trek_gebruiker_wissing_in",
    "AIDecision",
    "Agent",
    "AuditLog",
    "AuditService",
    "audit_rows_about_user",
    "C7ExecutionTask",
    "C7Workflow",
    "LawfulBasisMissingError",
    "LawfulBasisRegistry",
    "UserResponse",
    "get_current_tenant_id",
    "get_current_user",
    "require_admin_role",
    "get_db",
    "get_lawful_basis_registry",
]
