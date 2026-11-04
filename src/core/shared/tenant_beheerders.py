"""De telling van de beheerders van een tenant: EEN definitie, voor LAST_ADMIN en voor de AVG-wissing.

Een tenant houdt altijd minstens een actieve beheerder (ADR-039). Een wettelijke AVG-wissing van de
laatste beheerder wordt daarom nooit geblokkeerd maar wel gemeld; beide beslissingen moeten dezelfde
mensen tellen. Daarom staat de telling hier, in een neutrale module, en niet in `RBACService`: de
wisplekken (`governance.dsar_service`, `actors.gdpr_purge`) mogen `services.rbac_service` niet
importeren zonder een auth <-> governance-paar te maken (gemeten met
`tests/architecture/test_dsm016_no_auth_governance_circular.py`).

De module importeert bewust niets uit `src.*` (DSM: `shared` heeft fan-out 0,
`tests/architecture/test_dsm_grade_a_plus.py`); daarom staat de vraag als SQL en niet als ORM-query.
`tenant_id` is een gebonden parameter en staat op BEIDE tabellen in de voorwaarde.
"""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

BEHEERDERSROLNAMEN = frozenset({"admin", "system_admin", "tenantadmin"})

#: Auditactie na een AVG-wissing van de laatste beheerder: de wissing gaat door (wettelijk), maar het
#: platform moet weten dat de tenant geen beheerder meer heeft.
AUDITACTIE_TENANT_ZONDER_BEHEERDER = "tenant_zonder_beheerder"

# De platform-superuser telt NIET mee (F7): die beheert het platform, niet deze tenant.
_ACTIEVE_BEHEERDERS = text(
    """
    SELECT DISTINCT u.id
    FROM users u
    JOIN user_roles ur ON ur.user_id = u.id
    JOIN roles r ON r.id = ur.role_id
    WHERE u.tenant_id = :tenant_id
      AND r.tenant_id = :tenant_id
      AND r.is_active
      AND lower(r.name) IN :rolnamen
      AND u.is_active
      AND u.deleted_at IS NULL
      AND NOT u.is_superuser
    """
).bindparams(bindparam("rolnamen", expanding=True))


async def actieve_beheerders(db: AsyncSession, tenant_id: int) -> set[int]:
    """De actieve beheerders van de tenant: een beheerdersrol, actief, niet verwijderd."""
    rijen = await db.execute(
        _ACTIEVE_BEHEERDERS,
        {"tenant_id": tenant_id, "rolnamen": sorted(BEHEERDERSROLNAMEN)},
    )
    return {int(i) for i in rijen.scalars().all()}


async def is_laatste_beheerder(db: AsyncSession, tenant_id: int, user_id: int) -> bool:
    """Is deze gebruiker de ENIGE actieve beheerder van de tenant? Alleen lezen."""
    return await actieve_beheerders(db, tenant_id) == {user_id}
