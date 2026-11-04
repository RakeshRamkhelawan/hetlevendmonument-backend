"""`/me` beantwoordt de beheerdersvraag expliciet (ADR-036 OP-193).

De frontend leidde beheerderschap af uit de tokenscopes en dat kan niet: een beheerder
krijgt `users:read users:write workflows:read workflows:write` en niets dat zegt DAT hij
beheerder is (ADR-036 OP-186, geklemd door
`test_beheerdersscopes_blijven_wat_de_frontend_verwacht.py`). `get_me` geeft daarom
`is_admin` terug, berekend met de centrale `is_admin()`.

**De derde test is de belangrijkste en dekt een val die deze reeks bijna had gemaakt.**
`is_admin()` heeft twee helften: de rolnamen, en de superuser-bypass via
`getattr(user, "is_superuser", False)`. Die tweede helft werkt alleen als de vlag op het
BRONobject wordt gelezen -- `auth_service.UserResponse` heeft `is_superuser`, het
responsemodel in `api/auth/schemas.py` heeft het NIET. Was `is_admin` uit het responsemodel
berekend, dan had een platform-superuser zonder beheerdersrolnaam `is_admin=false` gekregen
terwijl de backend hem wel binnenlaat -- precies dezelfde divergentie tussen frontend en
backend als de storing die OP-193 oplost, alleen nieuw aangelegd. Die test faalt als iemand
de berekening naar het responsemodel verplaatst.
"""

from __future__ import annotations

import pytest

from src.core.api.auth.router_login import get_me
from src.core.auth.auth_service import UserResponse as BronUserResponse


def _bron(*, roles: list[str], is_superuser: bool = False) -> BronUserResponse:
    """Het object dat `get_current_user` daadwerkelijk teruggeeft."""
    return BronUserResponse(
        id=1,
        email="iemand@example.com",
        tenant_id=1,
        roles=roles,
        scopes=["users:read"],
        is_superuser=is_superuser,
    )


class _Rechtenrijen:
    """Wat `db.execute(...)` voor de rechtenlijst teruggeeft: rijen `(resource, action)`."""

    def __init__(self, rijen: list[tuple[str, str]]) -> None:
        self._rijen = rijen

    def all(self) -> list[tuple[str, str]]:
        return self._rijen


class _Db:
    """Sessie-stub: `get_me` leest sinds het rolmodel debiteuren ook de rechten van de rollen."""

    def __init__(self, rijen: list[tuple[str, str]] | None = None) -> None:
        self._rijen = rijen or []

    async def execute(self, _stmt: object) -> _Rechtenrijen:
        return _Rechtenrijen(self._rijen)


@pytest.mark.asyncio
async def test_een_beheerder_krijgt_is_admin_true() -> None:
    antwoord = await get_me(_bron(roles=["admin"]), _Db())  # type: ignore[arg-type]

    assert antwoord.is_admin is True, (
        "Een gebruiker met de rol `admin` krijgt geen beheerdersantwoord. De frontend "
        "stuurt hem dan naar /forbidden op alle zeven beheerdersroutes (ADR-036 OP-193)."
    )


@pytest.mark.asyncio
async def test_een_gewone_gebruiker_krijgt_is_admin_false() -> None:
    """De tweeling. Zonder deze helft is 'geef altijd true' een geldige oplossing, en dan
    is een dichte deur een openstaande deur geworden."""
    antwoord = await get_me(_bron(roles=["user"]), _Db())  # type: ignore[arg-type]

    assert antwoord.is_admin is False, (
        "Een gewone gebruiker krijgt een beheerdersantwoord. Dat opent zeven "
        "beheerdersroutes plus de HITL-goedkeuringsknoppen voor iedereen."
    )


@pytest.mark.asyncio
async def test_een_superuser_zonder_beheerdersrolnaam_krijgt_is_admin_true() -> None:
    """De val: deze slaagt alleen als de vlag uit het BRONobject wordt gelezen.

    Verplaatst iemand de berekening naar het responsemodel uit `api/auth/schemas.py` --
    dat geen `is_superuser` heeft -- dan wordt deze test ROOD, en dat is precies de
    bedoeling. De backend laat zo'n gebruiker wel binnen; de frontend zou hem buitensluiten.
    """
    antwoord = await get_me(_bron(roles=["viewer"], is_superuser=True), _Db())  # type: ignore[arg-type]

    assert antwoord.is_admin is True, (
        "Een platform-superuser zonder beheerdersrolnaam krijgt `is_admin=false`, terwijl "
        "`is_admin()` hem server-side WEL als beheerder ziet via de superuser-bypass. De "
        "frontend gelooft dan iets anders dan de backend afdwingt -- dezelfde soort "
        "divergentie als de storing die OP-193 oplost. Controleer of de vlag uit "
        "`auth_service.UserResponse` wordt berekend en niet uit het responsemodel."
    )


@pytest.mark.asyncio
async def test_de_overige_velden_blijven_staan() -> None:
    """`get_me` bouwt het antwoord nu met de hand; een vergeten veld verdwijnt stil."""
    bron = _bron(roles=["admin"])
    antwoord = await get_me(bron, _Db())  # type: ignore[arg-type]

    assert (antwoord.id, antwoord.email, antwoord.tenant_id) == (
        bron.id,
        bron.email,
        bron.tenant_id,
    )
    assert antwoord.roles == bron.roles
    assert antwoord.scopes == bron.scopes


# ============================================================================
# Het INLOGPAD, gevonden door de Gate 2-security-review van 2026-09-19
# ============================================================================


class _Rol:
    def __init__(self, naam: str) -> None:
        self.name = naam


class _OrmGebruiker:
    """Zoals `login()` de gebruiker uit de database krijgt: rollen zijn OBJECTEN."""

    def __init__(self, *rolnamen: str, is_superuser: bool = False) -> None:
        self.roles = [_Rol(n) for n in rolnamen]
        self.is_superuser = is_superuser


def test_is_admin_telt_geen_rolobjecten_alleen_strings() -> None:
    """De val op het inlogpad, vastgelegd zodat niemand hem opnieuw maakt.

    `login()` heeft het ORM-object bij de hand, en daar is `user.roles` een relatie naar
    `Role`-OBJECTEN. `is_admin()` telt alleen rolnamen die een STRING zijn
    (`_has_admin_role_name` filtert op `isinstance(r, str)`). Wie hier `is_admin(user)`
    schrijft met het ORM-object krijgt dus een `False` die van VORM klopt en van INHOUD
    niet: een echte beheerder zou op het inlogpad geen beheerder zijn, en alleen een
    superuser zou er nog doorheen komen.

    Deze test legt dat gedrag vast als FEIT, niet als wens. Gaat `is_admin()` ooit ook
    objecten tellen, dan wordt hij rood en hoort de omweg in `router_login.py` weg.
    """
    from src.core.auth.api_deps import is_admin

    assert is_admin(_OrmGebruiker("admin")) is False, (
        "`is_admin()` telt inmiddels rolOBJECTEN. Dan is de omweg met SimpleNamespace in "
        "`router_login.login()` overbodig geworden -- haal hem weg en werk deze test bij."
    )
    assert is_admin(_OrmGebruiker("viewer", is_superuser=True)) is True, (
        "De superuser-bypass leest `is_superuser` van het object; die helft hoort wel te "
        "werken op het ORM-object."
    )


@pytest.mark.asyncio
async def test_de_rechten_van_de_rollen_komen_mee() -> None:
    """Rolmodel debiteuren: de frontend zet de debiteurenknoppen op `permissions`."""
    db = _Db([("receivables", "write"), ("receivables", "read")])

    antwoord = await get_me(_bron(roles=["debiteuren"]), db)  # type: ignore[arg-type]

    assert antwoord.permissions == ["receivables:read", "receivables:write"]
