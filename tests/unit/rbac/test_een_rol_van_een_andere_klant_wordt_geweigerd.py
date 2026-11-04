"""Rechten wijzigen kan alleen op een rol van je EIGEN klant (ADR-036 OP-255 en OP-256).

WAT HIER MIS WAS
----------------
`add_permission_to_role` en `remove_permission_from_role` namen `role_id` rechtstreeks uit
het URL-pad (`api/v1/rbac/roles_router.py:154` en `:176`). Die router controleert wel of de
AANVRAGER `TENANT_ADMIN` is op zijn eigen klant, maar gaf daarna het rauwe nummer door: een
beheerder van klant A kon een `role_id` van klant B opgeven.

De ORM-tenantfilter vangt dat niet af. Die filtert bewust alleen SELECT/UPDATE/DELETE en
geen INSERT, en hij kan per sessie worden uitgezet met `TenantFilterBypass`. Een
schrijfactie mag niet afhangen van een filter op een leesactie -- daarom staat de controle
nu in de dienst zelf.

**Waarom de schrijfkant vandaag toch dicht zat, en waarom dat geen geruststelling is.**
`add_permission_to_role` faalde sowieso altijd: hij bouwde een `RolePermission` zonder
`tenant_id`, terwijl die kolom NOT NULL is (OP-255). Gemeten: `NotNullViolationError`,
gevangen, methode gaf `False`, endpoint gaf HTTP 400. De route was dus dicht door een BUG,
niet door een controle -- en wie die bug repareert zonder OP-256 opent hem. Daarom horen de
twee in een wijziging.

**404 en niet 403**, met opzet: een 403 bevestigt dat die rol ergens bestaat. Voor de
aanvrager bestaat een rol van een andere klant niet.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakte methode)
---------------------------------------------------------------------------
    `_rol_van_deze_klant`-aanroep uit `add_permission_to_role` gehaald    -> ROOD
    `_rol_van_deze_klant`-aanroep uit `remove_permission_from_role`      -> ROOD
    `tenant_id` weer NIET meegeven aan de `RolePermission`               -> ROOD (OP-255)
    een rol van de EIGEN klant                                           -> GROEN, geen weigering
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.core.services.rbac_service import RBACService

EIGEN_KLANT = 1
ANDERE_KLANT = 2
ROL_VAN_EEN_ANDERE_KLANT = 99


def _dienst_zonder_rol_in_deze_klant() -> RBACService:
    """Een dienst waarvan de rol-lookup NIETS oplevert -- de rol hoort bij een andere klant."""
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = None
    sessie = MagicMock()
    sessie.execute = AsyncMock(return_value=resultaat)
    sessie.commit = AsyncMock()
    sessie.rollback = AsyncMock()
    return RBACService(sessie)


def _dienst_met_rol_in_deze_klant() -> tuple[RBACService, MagicMock]:
    rol = MagicMock(id=7, tenant_id=EIGEN_KLANT)
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = rol
    sessie = MagicMock()
    sessie.execute = AsyncMock(return_value=resultaat)
    sessie.commit = AsyncMock()
    sessie.rollback = AsyncMock()
    sessie.add = MagicMock()
    return RBACService(sessie), sessie


@pytest.mark.asyncio
async def test_een_recht_toevoegen_aan_een_vreemde_rol_wordt_geweigerd() -> None:
    dienst = _dienst_zonder_rol_in_deze_klant()

    with pytest.raises(NotFoundError):
        await dienst.add_permission_to_role(
            ROL_VAN_EEN_ANDERE_KLANT, "agents", "read", tenant_id=EIGEN_KLANT
        )

    dienst.db.add.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_recht_afnemen_van_een_vreemde_rol_wordt_geweigerd() -> None:
    """Deze kant was WEL bereikbaar, dus hier telt de weigering het zwaarst."""
    dienst = _dienst_zonder_rol_in_deze_klant()

    with pytest.raises(NotFoundError):
        await dienst.remove_permission_from_role(
            ROL_VAN_EEN_ANDERE_KLANT, "agents", "read", tenant_id=EIGEN_KLANT
        )

    dienst.db.commit.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_recht_op_een_eigen_rol_wordt_geschreven_MET_de_klant() -> None:
    """De tegenrichting, plus OP-255: de rij krijgt een `tenant_id` en die is van de aanvrager."""
    dienst, sessie = _dienst_met_rol_in_deze_klant()

    gelukt = await dienst.add_permission_to_role(7, "agents", "read", tenant_id=EIGEN_KLANT)

    assert gelukt is True
    sessie.add.assert_called_once()
    geschreven = sessie.add.call_args[0][0]
    assert geschreven.tenant_id == EIGEN_KLANT, (
        "De permissierij is zonder klantnummer geschreven. Die kolom is NOT NULL, dus dit "
        "faalt in de database en het endpoint geeft altijd 400 (ADR-036 OP-255)."
    )
    assert geschreven.role_id == 7


@pytest.mark.asyncio
async def test_een_recht_afnemen_van_een_eigen_rol_mag_gewoon() -> None:
    dienst, sessie = _dienst_met_rol_in_deze_klant()

    gelukt = await dienst.remove_permission_from_role(7, "agents", "read", tenant_id=EIGEN_KLANT)

    assert gelukt is True
    sessie.commit.assert_awaited()
