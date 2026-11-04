"""De admin-checks van de codebase moeten hetzelfde antwoord geven (ADR-036 OP-40).

**De bevinding, gemeten en niet aangenomen.** Zeven plekken beslissen zelf of een gebruiker
beheerder is, in DRIE onverenigbare vocabulaires:

| # | Plek | Accepteert | Superuser |
| --- | --- | --- | --- |
| 1 | `auth/dependencies.is_tenant_admin` | `{admin, tenantadmin}`, kleine letters | ja |
| 2 | `auth/dependencies.require_admin` | idem, plus `role_id == 1` | ja |
| 3 | `api/dependencies.require_admin_role` | `{admin, system_admin}`, exacte case | NEE |
| 4 | `api/dependencies.require_admin_user` | `{admin}`, exacte case | ja |
| 5 | `api/v1/tenant_management/dependencies.require_admin` | `{admin, system_admin}` | NEE |
| 6 | `api/v1/user_management/dependencies.require_admin` | `{admin, system_admin}` | NEE |
| 7 | `api/v1/admin/dependencies.require_admin_role` | `{admin, system_admin}` | NEE |

Gevolg: een `system_admin` is beheerder in het hele `admin/`-domein maar wordt geweigerd op de
HITL-goedkeuringspoort, en een superuser wordt door vier van de zeven geweigerd.

**Een vierde as die niet in de registerrij stond en hier wel gemeten is: hoofdlettergevoeligheid.**
`RoleSeeder.DEFAULT_ROLES` maakt de standaardrol aan onder de naam `"Admin"` met hoofdletter
(`src/core/services/role_seeder.py:44`), en `AuthService` vult `UserResponse.roles` met
`[role.name for role in user.roles]` -- de ruwe databasenaam. Plek 1 en 2 zetten die naam om naar
kleine letters, de vijf andere vergelijken exact. Een gebruiker met alleen de geseede
standaard-beheerdersrol is dus beheerder voor twee van de zeven en gewoon gebruiker voor vijf.

**Wat deze test vastlegt.** Niet alleen DAT de zeven het eens zijn -- dan zou "weiger iedereen"
een geldige oplossing zijn -- maar ook WAT het antwoord moet zijn. Elke rij noemt de verwachte
uitkomst apart, zodat de test in beide richtingen bijt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

import pytest
from fastapi import HTTPException

from src.core.auth.auth_service import UserResponse


class _Check(NamedTuple):
    """Een van de gemeten aanroeppunten, met de manier om hem rechtstreeks te bevragen."""

    label: str
    call: Callable[[UserResponse], Awaitable[Any]]


async def _auth_is_tenant_admin(user: UserResponse) -> Any:
    """Plek 1: een predicaat en geen dependency, dus hier vertaald naar dezelfde vorm."""
    from src.core.auth.dependencies import is_tenant_admin

    if not is_tenant_admin(user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


async def _auth_require_admin(user: UserResponse) -> Any:
    from src.core.auth.dependencies import require_admin

    return await require_admin(user=user)


async def _api_require_admin_role(user: UserResponse) -> Any:
    from src.core.api.dependencies import require_admin_role

    return await require_admin_role(current_user=user, db=None)


async def _api_require_admin_user(user: UserResponse) -> Any:
    from src.core.api.dependencies import require_admin_user

    return await require_admin_user(current_user=user)


async def _tenant_management_require_admin(user: UserResponse) -> Any:
    from src.core.api.v1.tenant_management.dependencies import require_admin

    return await require_admin(current_user=user, db=None)


async def _user_management_require_admin(user: UserResponse) -> Any:
    from src.core.api.v1.user_management.dependencies import require_admin

    return await require_admin(current_user=user, db=None)


async def _admin_require_admin_role(user: UserResponse) -> Any:
    from src.core.api.v1.admin.dependencies import require_admin_role

    return await require_admin_role(current_user=user, db=None)


#: De expliciet benoemde verzameling waar deze tests over itereren. Een regel per gemeten plek --
#: en niet een glob of een zoekopdracht, zodat zichtbaar is WAT er bewaakt wordt.
ADMIN_CHECKS: tuple[_Check, ...] = (
    _Check("auth/dependencies.is_tenant_admin", _auth_is_tenant_admin),
    _Check("auth/dependencies.require_admin", _auth_require_admin),
    _Check("api/dependencies.require_admin_role", _api_require_admin_role),
    _Check("api/dependencies.require_admin_user", _api_require_admin_user),
    _Check("api/v1/tenant_management.require_admin", _tenant_management_require_admin),
    _Check("api/v1/user_management.require_admin", _user_management_require_admin),
    _Check("api/v1/admin.require_admin_role", _admin_require_admin_role),
)


def _user(roles: list[str], is_superuser: bool = False) -> UserResponse:
    return UserResponse(
        id=42,
        email="iemand@klant.example",
        tenant_id=7,
        roles=roles,
        is_superuser=is_superuser,
    )


async def _verdict(check: _Check, user: UserResponse) -> bool:
    """Laat deze plek deze gebruiker door? 403 is nee, alles anders is een echte fout."""
    try:
        await check.call(user)
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise
    return True


#: (naam, rollen, superuser, hoort-toegelaten-te-worden). De laatste kolom is de reden dat
#: "weiger alles" geen geldige oplossing is voor deze test.
_PROFILES: tuple[tuple[str, list[str], bool, bool], ...] = (
    ("system_admin", ["system_admin"], False, True),
    ("tenantadmin", ["tenantadmin"], False, True),
    ("admin", ["admin"], False, True),
    ("geseede rol Admin met hoofdletter", ["Admin"], False, True),
    ("superuser zonder beheerdersrol", ["viewer"], True, True),
    ("gewone gebruiker", ["viewer"], False, False),
    ("gebruiker zonder rollen", [], False, False),
)


@pytest.mark.unit
class TestEveryAdminCheckGivesTheSameAnswer:
    """Een gebruiker is beheerder of niet -- dat mag niet van het endpoint afhangen."""

    @pytest.mark.parametrize(
        ("naam", "roles", "is_superuser", "verwacht"),
        _PROFILES,
        ids=[p[0] for p in _PROFILES],
    )
    async def test_all_seven_checks_agree(
        self, naam: str, roles: list[str], is_superuser: bool, verwacht: bool
    ) -> None:
        user = _user(roles, is_superuser)

        uitkomsten = {check.label: await _verdict(check, user) for check in ADMIN_CHECKS}

        afwijkend = sorted(label for label, ok in uitkomsten.items() if ok is not verwacht)
        assert not afwijkend, (
            f"Profiel {naam!r} (roles={roles}, is_superuser={is_superuser}) hoort "
            f"{'toegelaten' if verwacht else 'geweigerd'} te worden, maar deze plekken doen het "
            f"anders: {afwijkend}. Volledige uitkomst: {uitkomsten}. Zolang zeven plekken elk hun "
            "eigen admin-definitie hebben, hangt wie beheerder is af van welk endpoint hij "
            "toevallig raakt -- zie ADR-036 OP-40."
        )


@pytest.mark.unit
class TestANonAdminIsRefusedAtEveryCallPoint:
    """De 403-regressietest, een regel per gemeten aanroeppunt.

    Dit is de tegenhanger van de test hierboven: de consolidatie mag de poort niet openzetten.
    Deze test is groen VOOR en NA de fix; hij bestaat om te betrappen dat een centrale definitie
    per ongeluk iedereen binnenlaat.
    """

    @pytest.mark.parametrize("check", ADMIN_CHECKS, ids=[c.label for c in ADMIN_CHECKS])
    async def test_a_plain_user_gets_403(self, check: _Check) -> None:
        toegelaten = await _verdict(check, _user(["viewer"]))

        assert toegelaten is False, (
            f"{check.label} liet een gebruiker met alleen de rol 'viewer' door. Een centrale "
            "admin-definitie mag de poort niet openzetten; dat zou de consolidatie erger maken "
            "dan de splitsing."
        )

    @pytest.mark.parametrize("check", ADMIN_CHECKS, ids=[c.label for c in ADMIN_CHECKS])
    async def test_a_user_without_any_role_gets_403(self, check: _Check) -> None:
        toegelaten = await _verdict(check, _user([]))

        assert toegelaten is False, f"{check.label} liet een gebruiker zonder enige rol door."
