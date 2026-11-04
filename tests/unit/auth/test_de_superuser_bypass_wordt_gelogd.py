"""De superuser-bypass logt een SUPERUSER_BYPASS-gebeurtenis (ADR-036 OP-199).

WAT HIER MIS WAS
----------------
`require_permission_with_tenant_bypass` slaat de hele rechtencontrole over zodra
`allow_super_admin` aan staat en de gebruiker `is_superuser` heeft
(`src/core/auth/dependencies.py:477-500`). Dat is een bewuste deur voor
platformbeheer, en de enige reden dat hij verantwoord is, is dat hij een auditregel
achterlaat. Die auditregel had NERGENS een werkende verificatie, en de twee tests die
hem zouden bewaken waren allebei buiten werking:

(a) `tests/unit/test_auth_dependencies_coverage.py::test_super_admin_bypass` stond op
    `pytest.mark.skip(reason="Flaky: ...")`. Die reden is een claim over het VERLEDEN en
    hij klopt niet meer: de test patcht `src.core.services.audit_service`, en die module
    bestaat niet. Hij zou vandaag deterministisch falen, niet wisselend. Hij toetste
    bovendien alleen `result == 1` en nooit dat er iets gelogd werd.

(b) `tests/security/test_owasp_a01_access_control.py::test_superuser_bypass_is_logged`
    struikelde op hetzelfde dode patchdoel. Erger nog: hij riep `log_security_event`
    ZELF aan en toetste daarna dat de mock was aangeroepen. Dat is een test die zijn
    eigen invoer aan beide kanten van de vergelijking verzint; het patchdoel repareren
    had hem groen gemaakt zonder dat hij de productiecode ooit raakte. Hij stond
    bovendien in `tests/security`, dat buiten de testpoort valt.

Deze test staat daarom in `tests/unit/`, BINNEN de poort, en loopt over de ECHTE
producent.

WAT DEZE TEST NIET BEWEERT
--------------------------
Dat de bypass vandaag bereikbaar is. Gemeten 2026-09-18: `require_permission_with_tenant_bypass`
heeft nul aanroepers in `src/` buiten zijn eigen definitie. Het pad is dood. Deze test
bewaakt dat de auditregel er nog staat als iemand het pad weer in gebruik neemt --
precies het moment waarop niemand meer nakijkt of dat ooit geregeld was.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    de `log_security_event`-aanroep uit de bypass verwijderd    -> ROOD
    `event_type` op iets anders dan SUPERUSER_BYPASS gezet      -> ROOD
    `if allow_super_admin and user.is_superuser` -> `if True`   -> ROOD (de twee negatieve richtingen)
    ongemuteerd                                                 -> GROEN
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.core.auth.dependencies as deps
from src.core.auth.rbac import Permission
from src.core.governance.services.audit_service import SecurityEvent

GEBRUIKER = 1


def _sessie_met(is_superuser: bool) -> MagicMock:
    gebruiker = MagicMock(id=GEBRUIKER, is_superuser=is_superuser)
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = gebruiker
    sessie = MagicMock()
    sessie.execute = AsyncMock(return_value=resultaat)
    return sessie


@pytest.mark.asyncio
async def test_de_bypass_laat_een_auditregel_achter() -> None:
    """De enige reden dat deze deur verantwoord is, is dat hij sporen achterlaat."""
    logboek = AsyncMock()
    with (
        patch.object(deps, "get_tenant_id", return_value=None),
        patch(
            "src.core.governance.services.audit_service.log_security_event",
            new=logboek,
        ),
    ):
        controleur = deps.require_permission_with_tenant_bypass(
            Permission.ADMIN, allow_super_admin=True
        )
        uitkomst = await controleur(user_id=GEBRUIKER, session=_sessie_met(True))

    assert uitkomst == GEBRUIKER
    logboek.assert_awaited_once()
    argumenten = logboek.await_args.kwargs
    assert argumenten["event_type"] == SecurityEvent.SUPERUSER_BYPASS, (
        "De bypass logt iets anders dan SUPERUSER_BYPASS. Dan is hij in het auditspoor "
        "niet terug te vinden als wat hij is (ADR-036 OP-199)."
    )
    assert argumenten["user_id"] == GEBRUIKER


@pytest.mark.asyncio
async def test_zonder_allow_super_admin_gaat_hij_door_de_gewone_controle() -> None:
    """Tegenrichting 1: de vlag uit betekent geen bypass, ook voor een superuser."""
    logboek = AsyncMock()
    gewone_controle = AsyncMock(return_value=GEBRUIKER)
    with (
        patch.object(deps, "get_tenant_id", return_value=None),
        patch(
            "src.core.governance.services.audit_service.log_security_event",
            new=logboek,
        ),
        patch.object(deps, "require_permission", return_value=gewone_controle),
    ):
        controleur = deps.require_permission_with_tenant_bypass(
            Permission.ADMIN, allow_super_admin=False
        )
        await controleur(user_id=GEBRUIKER, session=_sessie_met(True))

    gewone_controle.assert_awaited_once()
    logboek.assert_not_awaited()


@pytest.mark.asyncio
async def test_een_gewone_gebruiker_gaat_door_de_gewone_controle() -> None:
    """Tegenrichting 2: zonder deze helft zou 'log altijd' een geldige oplossing zijn."""
    logboek = AsyncMock()
    gewone_controle = AsyncMock(return_value=GEBRUIKER)
    with (
        patch.object(deps, "get_tenant_id", return_value=None),
        patch(
            "src.core.governance.services.audit_service.log_security_event",
            new=logboek,
        ),
        patch.object(deps, "require_permission", return_value=gewone_controle),
    ):
        controleur = deps.require_permission_with_tenant_bypass(
            Permission.ADMIN, allow_super_admin=True
        )
        await controleur(user_id=GEBRUIKER, session=_sessie_met(False))

    gewone_controle.assert_awaited_once()
    logboek.assert_not_awaited()
