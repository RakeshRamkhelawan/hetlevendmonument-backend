"""De gezaaide beheerder wordt aan de rol `admin` gekoppeld -- en alleen als hij er geen heeft.

WAAROM DEZE TEST BESTAAT
------------------------
Gemeten 2026-09-17 op staging: `seed.py` maakt de beheerder aan met `is_superuser = True`,
`ensure_default_roles` maakt de rollen aan, en NIETS koppelde de twee. `user_roles` was
leeg. Het token krijgt zijn scopes uitsluitend uit `user.roles` (`router_login.py:133`) en
`scope_validator` kent geen uitzondering voor `is_superuser`, dus de beheerder kon inloggen
en daarna op elk endpoint met een scope een 403:

    WARNING | User 1 missing scope OAuth2Scope.AGENTS_READ

De tweede helft is minstens zo belangrijk als de eerste: dit is een BOOTSTRAP en geen
handhaving. Heeft het account al een rol, dan blijft die staan -- anders krijgt een
beheerder wiens rechten bewust zijn ingetrokken ze bij de eerstvolgende herstart stil
terug, en dat is een rechtenverhoging die niemand heeft aangevraagd.

Deze tests draaien de functie ECHT; de sessie en de RBAC-dienst zijn testdubbels, want de
grens die hier telt is "welke aanroep doet hij wel en niet", niet de SQL.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.app_lifespan import _koppel_de_gezaaide_beheerder


def _sessie_die_dit_teruggeeft(gebruiker: object | None) -> MagicMock:
    """Een sessiedubbel waarvan `execute(...).scalar_one_or_none()` `gebruiker` oplevert."""
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = gebruiker
    sessie = MagicMock()
    sessie.execute = AsyncMock(return_value=resultaat)
    return sessie


def _rbac() -> MagicMock:
    dienst = MagicMock()
    dienst.assign_role = AsyncMock(return_value=True)
    dienst.ensure_platform_role = AsyncMock()
    return dienst


@pytest.mark.asyncio
async def test_een_beheerder_zonder_rollen_krijgt_de_rol_admin() -> None:
    beheerder = SimpleNamespace(id=7, roles=[])
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(beheerder), rbac, 3)

    rbac.assign_role.assert_awaited_once_with(7, "admin", 3)


@pytest.mark.asyncio
async def test_een_beheerder_die_al_een_rol_heeft_wordt_ongemoeid_gelaten() -> None:
    """De tegenrichting: zonder deze helft is 'altijd admin toekennen' een geldige fix."""
    beheerder = SimpleNamespace(id=7, roles=[SimpleNamespace(name="user")])
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(beheerder), rbac, 3)

    rbac.assign_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_zonder_gezaaide_beheerder_gebeurt_er_niets() -> None:
    """Een tenant zonder dat e-mailadres is geen fout -- en zeker geen reden om te raden."""
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(None), rbac, 3)

    rbac.assign_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_een_nieuwe_gezaaide_platformbeheerder_met_de_vlag_krijgt_ook_system_admin() -> None:
    """Brief 2026-10-19: het gezag om platformrollen uit te delen is de ROL; de vlag alleen is dat niet."""
    beheerder = SimpleNamespace(id=7, roles=[], is_superuser=True)
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(beheerder), rbac, 3)

    assert [c.args for c in rbac.assign_role.await_args_list] == [
        (7, "admin", 3),
        (7, "system_admin", 3),
    ]


@pytest.mark.asyncio
async def test_de_platformrol_wordt_als_rij_gezaaid_voor_hij_wordt_gekoppeld() -> None:
    beheerder = SimpleNamespace(id=7, roles=[], is_superuser=True)
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(beheerder), rbac, 3)

    rbac.ensure_platform_role.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_een_gezaaide_beheerder_zonder_de_vlag_krijgt_alleen_admin() -> None:
    """De tegenrichting: zonder deze helft is 'altijd system_admin' een geldige fix."""
    beheerder = SimpleNamespace(id=7, roles=[], is_superuser=False)
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(beheerder), rbac, 3)

    assert [c.args for c in rbac.assign_role.await_args_list] == [(7, "admin", 3)]


@pytest.mark.asyncio
async def test_een_bestaande_platformbeheerder_met_een_rol_wordt_niet_bij_een_herstart_verhoogd() -> None:
    """Account 1 en 101 in de ontwikkeldatabase (vlag, rol admin): de seed wijzigt hun rijen niet."""
    beheerder = SimpleNamespace(id=1, roles=[SimpleNamespace(name="admin")], is_superuser=True)
    rbac = _rbac()

    await _koppel_de_gezaaide_beheerder(_sessie_die_dit_teruggeeft(beheerder), rbac, 3)

    rbac.assign_role.assert_not_awaited()
