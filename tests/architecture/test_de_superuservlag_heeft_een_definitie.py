"""`is_superuser` wordt maar op EEN plek tot een besluit gemaakt (ADR-036 OP-189).

WAAROM DEZE BEWAKER BESTAAT
---------------------------
Dit systeem heeft twee privilege-assen. `is_admin` beantwoordt "mag deze gebruiker beheren
BINNEN zijn tenant" en is in september 2026 geconsolideerd (OP-40). De tweede as --
`User.is_superuser`, oftewel "mag deze gebruiker de TENANT-GRENS over" -- bleef daarbij
ongemoeid en stond op 17 beslissende plekken in 9 bestanden los uitgeschreven. Dat is een
nette ordening met een deur ernaast: wie hier later een voorwaarde aan toevoegt, zet hem op
de plek die hij toevallig openhad. Precies het patroon uit OP-254, waar een verplichte stap
op EEN van de zes schrijfplekken stond.

Sinds 2026-09-18 gaat die vraag door `src.core.auth.dependencies.is_platform_superuser`.

Deze bewaker toetst STRUCTUUR: hij zoekt met de AST naar een LEESACTIE `<iets>.is_superuser`.
Een string (`"is_superuser"` als dict-sleutel in de seeder), een kolomdefinitie en een
keyword-argument zijn geen leesactie en komen er dus niet in -- dat scheelt een
uitzonderingslijst die groter is dan wat hij bewaakt.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    `is_platform_superuser(current_user)` terug naar `current_user.is_superuser`
        in `users_detail_router.py`      -> ROOD
        in `tenants_list_router.py`      -> ROOD
        in `domain_packs.py`             -> ROOD
    ongemuteerd, met de drie gedateerde uitzonderingen  -> GROEN
    `is_platform_superuser` leest de vlag niet meer     -> ROOD (tegenrichting)
    een uitzondering die nergens meer bestaat           -> ROOD (staleness)
"""

from __future__ import annotations

import ast
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2]
_BRON = _WORTEL / "src"

#: Migraties lezen de vlag niet; ze maken de kolom. Die horen hier niet.
_BUITEN_BESCHOUWING = "src/alembic/"

#: Gedateerde uitzonderingen (2026-09-18), met een reden PER regel. Sleutel is
#: `bestand::functie`, niet het bestand -- een uitzondering mag nooit een heel bestand
#: doof maken (die fout is bij de OP-258-guard gemeten en gecorrigeerd).
KNOWN_LOSSE_LEZERS: dict[str, str] = {
    "src/core/auth/auth_service.py::get_user_by_id": (
        "kopieert de vlag naar de `UserResponse`-DTO, neemt geen besluit -- OP-189"
    ),
    "src/core/auth/auth_service.py::get_user_by_email": (
        "idem, het tweede opzoekpad -- OP-189"
    ),
    "src/core/services/rbac_service.py::_gebruikers_met_rolnamen": (
        "haalt de vlag op als INVOER voor `telt_als_platformbeheerder`, de ene definitie van "
        "'doel is platformbeheerder' (rol OF vlag, brief 2026-10-19); het besluit staat daar -- OP-189"
    ),
    "src/core/copilot/proactive/deps.py::get_primary_admin_user_id": (
        "`User.is_superuser.is_(True)` is een SQL-kolomexpressie op de KLASSE, geen "
        "gebruikersobject; `is_platform_superuser` kan daar niets betekenen -- OP-189"
    ),
}


def _losse_lezers() -> dict[str, list[int]]:
    """{bestand::functie: [regels]} voor elke leesactie `<iets>.is_superuser` in `src/`."""
    gevonden: dict[str, list[int]] = {}

    def _is_kolomselectie(knoop: ast.AST) -> bool:
        """Is dit een `load_only(...)`/`defer(...)`-aanroep, oftewel een KOLOMKEUZE?

        Toegevoegd 2026-09-19. De docstring hierboven zegt al dat een kolomdefinitie geen
        leesactie is, maar de implementatie ving `User.is_superuser` binnen
        `load_only(...)` wel -- en dat is geen besluit over een gebruiker maar een keuze
        welke KOLOM uit de database komt. Gemeten geval: `router_login.py:265` moest die
        kolom juist laden, omdat een kolom die daar ONTBREEKT niet afwezig is maar
        uitgesteld, en hem daarna lezen in een asynchrone sessie een `MissingGreenlet`
        geeft. De bewaker verbood daarmee precies de regel die de vlag correct beschikbaar
        maakt voor de centrale definitie.

        Dit is een verSMALling naar de gedocumenteerde bedoeling, geen verzwakking: een
        leesactie op een INSTANTIE (`user.is_superuser`) en een filter
        (`.where(User.is_superuser == True)`) blijven gewoon betrapt.
        """
        return (
            isinstance(knoop, ast.Call)
            and isinstance(knoop.func, (ast.Name, ast.Attribute))
            and (
                knoop.func.id if isinstance(knoop.func, ast.Name) else knoop.func.attr
            )
            in {"load_only", "defer", "undefer"}
        )

    def loop(knoop: ast.AST, bestand: str, functie: str) -> None:
        for kind in ast.iter_child_nodes(knoop):
            naam = functie
            if _is_kolomselectie(kind):
                continue
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                naam = kind.name
            elif (
                isinstance(kind, ast.Attribute)
                and kind.attr == "is_superuser"
                and isinstance(kind.ctx, ast.Load)
            ):
                gevonden.setdefault(f"{bestand}::{functie}", []).append(kind.lineno)
            loop(kind, bestand, naam)

    for pad in _BRON.rglob("*.py"):
        relatief = pad.relative_to(_WORTEL).as_posix()
        if relatief.startswith(_BUITEN_BESCHOUWING):
            continue
        try:
            # utf-8-sig: `api/domain_packs.py` begint met een BOM.
            boom = ast.parse(pad.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        loop(boom, relatief, "<modulebody>")
    return gevonden


def test_geen_nieuwe_losse_superusercheck() -> None:
    """Een nieuw besluit op deze as gaat door de centrale definitie."""
    gevonden = _losse_lezers()
    nieuw = {p: r for p, r in gevonden.items() if p not in KNOWN_LOSSE_LEZERS}

    assert not nieuw, (
        f"Deze plekken lezen `is_superuser` zelf: {nieuw}. Gebruik "
        "`src.core.auth.dependencies.is_platform_superuser` (via `auth.api_deps`), zodat een "
        "voorwaarde die later bij deze as hoort op EEN plek staat (ADR-036 OP-189)."
    )


def test_de_uitzonderingen_zijn_niet_verouderd() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    gevonden = _losse_lezers()
    verdwenen = [p for p in KNOWN_LOSSE_LEZERS if p not in gevonden]

    assert not verdwenen, (
        f"Deze plekken lezen `is_superuser` niet meer: {verdwenen}. Haal ze uit "
        "KNOWN_LOSSE_LEZERS."
    )


def test_de_centrale_definitie_leest_de_vlag_echt() -> None:
    """Tegenrichting: zonder deze helft is 'niemand leest de vlag' een geldige oplossing.

    `is_platform_superuser` gebruikt `getattr(user, "is_superuser", False)` en niet de
    attribuutvorm, juist zodat hij zijn eigen bewaker niet overtreedt. Daarom wordt hij hier
    op GEDRAG getoetst en niet op vorm -- een AST-controle zou hier niets vinden en dat zou
    als groen lezen.
    """
    from src.core.auth.dependencies import is_platform_superuser

    class _Platformbeheerder:
        is_superuser = True

    class _GewoneGebruiker:
        is_superuser = False

    class _ZonderVlag:
        pass

    assert is_platform_superuser(_Platformbeheerder()) is True
    assert is_platform_superuser(_GewoneGebruiker()) is False
    assert is_platform_superuser(_ZonderVlag()) is False, (
        "Een object zonder de vlag moet NEE krijgen. Fail-secure: een DTO waar het veld "
        "ontbreekt mag nooit de tenant-grens over."
    )
