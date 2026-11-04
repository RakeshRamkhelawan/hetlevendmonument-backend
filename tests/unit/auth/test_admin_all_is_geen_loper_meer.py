"""`admin:*` is geen loper meer en wordt niet op rolnaam uitgedeeld (ADR-036 OP-186).

**De bevinding.** `scope_validator.py` had `if scope in jwt_scopes or
OAuth2Scope.ADMIN_ALL.value in jwt_scopes: continue`. Die `or`-tak liet EEN scope elke
andere scope-controle overslaan, over 306 endpoints, zonder enige databasecheck. En die
scope werd uitgedeeld op ROLNAAM: heette een van je rollen `admin`, dan zat hij in je token.
Twee producenten deden dat -- `router_login._get_user_scopes` en
`auth_service._get_role_scopes` -- en beide produceerden letterlijk `"admin:*"`.

**Waarom dit veilig kon.** De rij van OP-186 stelt als voorwaarde dat OP-187 per tenant
GEMETEN is. Gemeten 2026-09-11 en herhaald 2026-09-15 tegen de live database: de rol `admin`
draagt een `*`/`*`-permissierij en heeft beide bestaande beheerders; de permissieloze rollen
(`system_admin`, `user`) hebben nul gebruikers. De regressielijst is dus leeg -- echte
beheerders houden toegang via de databasefallback, die op `resource == "*"` en
`action == "*"` matcht.

**Beide richtingen, met opzet.** Zonder de tegentests zou "weiger alles" of "deel nooit een
scope uit" deze tests halen, en dan is de applicatie stuk in plaats van veilig.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

from src.core.auth.scopes import OAuth2Scope


def _module_ast(module) -> ast.Module:
    return ast.parse(inspect.getsource(module))


def test_de_scope_validator_heeft_geen_bypass_meer_op_admin_all() -> None:
    """De `or`-tak die elke controle oversloeg, MOET weg zijn.

    STRUCTUREEL getoetst met een AST-parse en niet met een tekstzoektocht. De eerste versie
    zocht de string `or OAuth2Scope.ADMIN_ALL.value in jwt_scopes` in de broncode -- en
    faalde op de TOELICHTING die de oude regel CITEERT om uit te leggen wat er weg is.
    Commentaar staat niet in een AST, een handeling wel. Dit is dezelfde holle vorm waar
    quality-gates.md voor waarschuwt, hier tweemaal op een dag in gelopen.
    """
    from src.core.auth import scope_validator

    for knoop in ast.walk(_module_ast(scope_validator)):
        if not isinstance(knoop, ast.BoolOp):
            continue
        namen = {
            n.attr
            for deel in knoop.values
            for n in ast.walk(deel)
            if isinstance(n, ast.Attribute)
        }
        assert "ADMIN_ALL" not in namen, (
            f"Op regel {knoop.lineno} staat ADMIN_ALL weer in een `and`/`or`-voorwaarde. "
            "Een scope die elke andere scope-controle overslaat, geeft volledige "
            "compromittering en niet alleen cross-tenant lezen (ADR-036 OP-186)."
        )


def test_de_fast_path_toetst_nog_steeds_de_gevraagde_scope() -> None:
    """De andere richting: zonder deze zou 'verwijder de hele fast path' halen."""
    from src.core.auth import scope_validator

    gevonden = any(
        isinstance(k, ast.Compare)
        and isinstance(k.left, ast.Name)
        and k.left.id == "scope"
        and any(isinstance(op, ast.In) for op in k.ops)
        for k in ast.walk(_module_ast(scope_validator))
    )
    assert gevonden, (
        "De snelle controle `scope in jwt_scopes` is verdwenen. Zonder haar valt elke "
        "aanroep terug op de database en is de reparatie een prestatieprobleem."
    )


def _nep_gebruiker(*rolnamen: str):
    """Een gebruiker met alleen de velden die `_get_user_scopes` aanraakt."""
    return SimpleNamespace(roles=[SimpleNamespace(name=n) for n in rolnamen])


@pytest.mark.asyncio
async def test_inloggen_deelt_admin_all_niet_meer_uit_op_rolnaam() -> None:
    """Producent 1, op GEDRAG getoetst en niet op broncode.

    De eerste versie van deze test las de broncode en zocht de tekst "ADMIN_ALL". Die
    faalde op de TOELICHTING die de reparatie uitlegt -- precies de holle vorm uit
    quality-gates.md: tekst doorzoeken waar je een handeling moet toetsen.
    """
    from src.core.api.auth.router_login import _get_user_scopes

    scopes = await _get_user_scopes(_nep_gebruiker("admin"))

    assert OAuth2Scope.ADMIN_ALL.value not in scopes, (
        f"Een rol met de NAAM `admin` levert weer {OAuth2Scope.ADMIN_ALL.value!r} op, zonder "
        "dat de database is geraadpleegd. Ongeveer 70 endpoints EISEN die scope; die staan "
        "dan open voor iedereen met een zo genoemde rol (ADR-036 OP-186)."
    )


@pytest.mark.asyncio
async def test_inloggen_geeft_een_beheerder_nog_steeds_zijn_gewone_scopes() -> None:
    """De andere richting -- anders zou 'deel niets uit' de test hierboven halen."""
    from src.core.api.auth.router_login import _get_user_scopes

    scopes = await _get_user_scopes(_nep_gebruiker("admin"))

    for scope in (
        OAuth2Scope.USERS_WRITE.value,
        OAuth2Scope.WORKFLOWS_READ.value,
        OAuth2Scope.WORKFLOWS_WRITE.value,
    ):
        assert scope in scopes, (
            f"De scope {scope!r} is uit het inlogpad verdwenen. De reparatie mag de loper "
            "weghalen, niet de legitieme rechten van een beheerder."
        )


@pytest.mark.asyncio
async def test_een_gewone_gebruiker_krijgt_geen_beheerdersscopes() -> None:
    """Derde richting: de reparatie mag ook niemand rechten TOEVOEGEN."""
    from src.core.api.auth.router_login import _get_user_scopes

    scopes = await _get_user_scopes(_nep_gebruiker("user"))

    assert OAuth2Scope.ADMIN_ALL.value not in scopes
    assert OAuth2Scope.USERS_WRITE.value not in scopes, (
        "Een gewone gebruiker kreeg schrijfrechten op gebruikers."
    )


def test_de_tweede_producent_deelt_admin_all_ook_niet_meer_uit() -> None:
    """Producent 2: `auth_service._get_role_scopes` -- dezelfde string, andere plek."""
    from src.core.auth.auth_service import AuthService

    boom = ast.parse(textwrap.dedent(inspect.getsource(AuthService._get_role_scopes)))
    constanten = {
        k.value for k in ast.walk(boom) if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    assert "admin:*" not in constanten, (
        "De tweede producent deelt de loper weer uit. Deze werd bij het eerste onderzoek "
        "bijna over het hoofd gezien omdat hij in een ANDER bestand staat dan de eerste."
    )


def test_de_tweede_producent_houdt_de_concrete_beheerdersscopes() -> None:
    """De andere richting voor producent 2."""
    from src.core.auth.auth_service import AuthService

    boom = ast.parse(textwrap.dedent(inspect.getsource(AuthService._get_role_scopes)))
    constanten = {
        k.value for k in ast.walk(boom) if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    for scope in ("users:write", "roles:write", "audit:read"):
        assert scope in constanten, (
            f"De scope {scope!r} is verdwenen uit de rolafbeelding; dan verliest een "
            "beheerder rechten die hij wel hoort te hebben."
        )
