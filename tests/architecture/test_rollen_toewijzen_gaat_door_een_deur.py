"""Rollen toewijzen gebeurt via `RBACService`, niet met rauwe SQL op `user_roles` (OP-258).

WAAROM DEZE BEWAKER BESTAAT
---------------------------
Tot 2026-09-18 bestond "de rolset van een gebruiker vervangen" TWEE keer: in
`RBACService`, en met een eigen `user_roles.delete()` + N `insert()` in
`api/v1/user_management/crud_router.py`. Dat tweede pad was geen klantlek en niet
ongeaudit -- het controleerde `Role.tenant_id` en schreef een auditregel. Het probleem is
de VORM. Bij OP-254 bleek dat een noodzakelijke stap (cache-invalidatie) op EEN van de zes
schrijfplekken stond, precies omdat de andere vijf niet door dezelfde deur gingen. Wie de
volgende verplichting toevoegt -- een auditregel, een governance-event, een invalidatie --
zet hem op de deur die hij toevallig openhad.

Deze bewaker toetst STRUCTUUR, geen tekst: hij zoekt met de AST naar een aanroep
`<tabel>.insert() / .delete() / .update()` op een van de bewaakte tabellen. Een
toelichting die zo'n aanroep in PROZA noemt (zoals de comment in `crud_router.py:517`)
houdt hem dus niet groen -- dat was de terugkerende faalvorm in
`quality-gates.md`.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    `user_roles.delete()` terug in `crud_router.assign_user_roles`        -> ROOD
    `user_roles.insert()` terug in `crud_router.assign_user_roles`        -> ROOD
    `role_permissions.delete()` in `crud_router.assign_user_roles`        -> ROOD
    ongemuteerd, met de twee gedateerde uitzonderingen                    -> GROEN
    `rbac_service.py` schrijft zelf niet meer (tegenrichting)             -> ROOD
    een uitzondering die nergens meer bestaat (staleness)                 -> ROOD

De eerste versie van deze bewaker had een uitzondering per BESTAND. Alle drie de
voorwaartse mutaties bleven toen GROEN, omdat `crud_router.py` al op de lijst stond wegens
`create_user`. Dat is hier opgeschreven omdat het de reden is dat de sleutel
`bestand::functie` is, en niet een detail van de implementatie.
"""

from __future__ import annotations

import ast
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2]
_BRON = _WORTEL / "src"

#: De koppeltabellen waar een rolwijziging op neerkomt. Deze verzameling staat hier
#: EXPLICIET zodat het mutatiebewijs hierboven een regel per element kan hebben.
_BEWAAKTE_TABELLEN = frozenset({"user_roles", "role_permissions"})

#: De schrijfwerkwoorden van SQLAlchemy Core op een `Table`.
_SCHRIJFWERKWOORDEN = frozenset({"insert", "delete", "update"})

#: De enige plek waar zo'n schrijfactie hoort.
_DE_DEUR = "src/core/services/rbac_service.py"

#: Gedateerde uitzonderingen, met een reden PER regel (2026-09-18). De sleutel is
#: `bestand::functie` en NIET alleen het bestand -- dat is gemeten noodzakelijk: met een
#: sleutel per bestand stond `crud_router.py` al op de lijst wegens `create_user`, en
#: bleven alle drie de voorwaartse mutaties in `assign_user_roles` GROEN. De guard was dan
#: blind op precies het bestand waar OP-258 vandaan kwam.
#: Beide zijn dezelfde vorm: de rol wordt toegekend BINNEN de transactie die de gebruiker
#: aanmaakt, voor de enige `commit()`. `RBACService.vervang_rollen` committeert zelf, dus
#: die erin schuiven zou de gebruiker halverwege vastleggen en de aanmaak niet langer
#: atomair maken. Dat is een eigen wijziging met een eigen risico, geen bijvangst.
KNOWN_RAUWE_ROLSCHRIJVERS: dict[str, str] = {
    "src/core/api/v1/user_management/crud_router.py::create_user": (
        "create_user kent rollen toe binnen de aanmaaktransactie, voor de enige commit "
        "-- OP-258, apart besluit"
    ),
    "src/core/auth/auth_service.py::create_user": (
        "AuthService.create_user doet hetzelfde bij registratie -- OP-258, apart besluit"
    ),
}


def _schrijfacties_per_plek() -> dict[str, list[int]]:
    """{bestand::functie: [regelnummers]} voor elke rauwe schrijfactie buiten de deur.

    De sleutel bevat de OMSLUITENDE functie, zodat een uitzondering nooit een heel bestand
    doof maakt. Het doorlopen gebeurt expliciet-recursief en niet met `ast.walk()` vanaf
    een functieknoop, omdat `walk()` geneste functies niet van hun ouder onderscheidt.
    """
    gevonden: dict[str, list[int]] = {}

    def loop(knoop: ast.AST, bestand: str, functie: str) -> None:
        for kind in ast.iter_child_nodes(knoop):
            naam = functie
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                naam = kind.name
            elif isinstance(kind, ast.Call) and isinstance(kind.func, ast.Attribute):
                doel = kind.func.value
                if (
                    kind.func.attr in _SCHRIJFWERKWOORDEN
                    and isinstance(doel, ast.Name)
                    and doel.id in _BEWAAKTE_TABELLEN
                ):
                    gevonden.setdefault(f"{bestand}::{functie}", []).append(kind.lineno)
            loop(kind, bestand, naam)

    for pad in _BRON.rglob("*.py"):
        relatief = pad.relative_to(_WORTEL).as_posix()
        if relatief == _DE_DEUR:
            continue
        try:
            boom = ast.parse(pad.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        loop(boom, relatief, "<modulebody>")
    return gevonden


def test_geen_nieuwe_rauwe_rolschrijver() -> None:
    """Een rolwijziging buiten `RBACService` is geen tweede deur meer."""
    gevonden = _schrijfacties_per_plek()
    nieuw = {p: r for p, r in gevonden.items() if p not in KNOWN_RAUWE_ROLSCHRIJVERS}

    assert not nieuw, (
        "Rauwe schrijfacties op een rollentabel (bestand::functie) buiten "
        f"{_DE_DEUR}: {nieuw}. Gebruik `RBACService` (bijvoorbeeld `vervang_rollen`), zodat "
        "een verplichting die later bij een rolwijziging hoort op EEN plek staat "
        "(ADR-036 OP-258)."
    )


def test_de_uitzonderingen_zijn_niet_verouderd() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    gevonden = _schrijfacties_per_plek()
    verdwenen = [p for p in KNOWN_RAUWE_ROLSCHRIJVERS if p not in gevonden]

    assert not verdwenen, (
        f"Deze plekken schrijven niet langer rauw op een rollentabel: {verdwenen}. "
        "Haal ze uit KNOWN_RAUWE_ROLSCHRIJVERS."
    )


def test_de_deur_zelf_schrijft_wel() -> None:
    """De tegenrichting: `RBACService` MOET deze schrijfacties bevatten.

    Zonder deze helft zou 'nergens meer rauw schrijven' een geldige oplossing zijn --
    inclusief de variant waarin de functionaliteit gewoon weg is.
    """
    boom = ast.parse((_WORTEL / _DE_DEUR).read_text(encoding="utf-8"))
    werkwoorden = {
        k.func.attr
        for k in ast.walk(boom)
        if isinstance(k, ast.Call)
        and isinstance(k.func, ast.Attribute)
        and isinstance(k.func.value, ast.Name)
        and k.func.value.id in _BEWAAKTE_TABELLEN
        and k.func.attr in _SCHRIJFWERKWOORDEN
    }

    assert {"insert", "delete"} <= werkwoorden, (
        f"{_DE_DEUR} schrijft niet meer op de rollentabellen ({werkwoorden}); dan bewaakt "
        "deze guard een deur die nergens meer heen gaat."
    )
