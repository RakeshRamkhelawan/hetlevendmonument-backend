"""Een `Role(...)` wordt in src/ alleen aangemaakt op een benoemde plek (LOW-1, beveiligingsreview).

**Wat hier bewaakt wordt.** De bescherming van de gereserveerde rolnaam (`system_admin` e.d.) zit
uitsluitend in `RBACService.create_role`. Een toekomstig pad dat zelf `Role(...)` aanmaakt, loopt
daar omheen en geeft een klantbeheerder opnieuw een platformrol. Deze guard laat een nieuwe
`Role(...)`-aanroep in `src/` pas toe als hij op `ALLOWED_ROLE_CONSTRUCTIONS` staat, met een reden.

**Structuur, geen tekst.** De bron wordt met `ast` gelezen; alleen een `ast.Call` waarvan de
aanroepnaam `Role` is (`Role(...)` of `x.Role(...)`) telt. Docstrings en comments zijn geen
`Call` en tellen dus niet mee (de comment in `auth_service.py` die `Role(name=...)` noemt, staat
daarom niet op de lijst). De omsluitende functie wordt met EXPLICIETE recursie bijgehouden:
`ast.walk()` vanaf een functieknoop onderscheidt een geneste functie niet van zijn ouder.

**De sleutel is `bestand::functie`, nooit alleen het bestand.** `rbac_service.py` staat al op de
lijst voor twee functies; een lijst op bestandsniveau liet een derde `Role(...)` in dat bestand
ongezien (zie quality-gates.md, aanscherping 2026-09-18).

**Scope is `src/`.** `tests/`, `alembic/` en migraties maken legitiem `Role(...)` aan en worden
niet gelezen: de scan loopt over `git ls-files src`.

**Wat deze guard NIET ziet:** een aanroep via een alias (`from ... import Role as R`) wordt apart
afgekeurd (`test_role_is_never_imported_under_an_alias`); `getattr`, `type(x)(...)` of een
dynamisch opgehaalde klasse niet. Ruwe SQL (`INSERT INTO roles`) valt buiten deze guard.

**Autouse-fixtures:** `tests/conftest.py` (omgeving, singletons) raakt de bron niet; deze module
leest alleen bestanden. Er wordt niets gepatcht.

**Mutatiebewijs, gemeten 2026-10-04 met een scratchscript dat `test_no_unlisted_...` en
`test_every_allowed_...` aanriep op een in het geheugen gemuteerde kopie van de echte bronnen
(nooit een bestand in src/ aangeraakt). Een regel per element:**

| Element | Mutatie | Uitkomst |
| --- | --- | --- |
| patroon `Role(`, bestand niet op de lijst | extra functie met `Role(...)` in `users/shared.py` | ROOD |
| idem | idem in `auth/auth_service.py` | ROOD |
| bestand op de lijst (`rbac_service.py`) | tweede `Role(...)` in `bulk_assign_roles` | ROOD |
| bestand op de lijst (`rbac_service.py`) | extra nieuwe functie met `Role(...)` | ROOD |
| bestand op de lijst (`ensure_demo_user.py`) | extra nieuwe functie met `Role(...)` | ROOD |
| uitzondering `rbac_service.py::create_role` | `Role(...)` daaruit weg -> staleness | ROOD |
| uitzondering `rbac_service.py::ensure_default_roles` | idem | ROOD |
| uitzondering `ensure_demo_user.py::_zorg_voor_rol_en_gebruiker` | idem | ROOD |
| alias | `import Role as R` | ROOD |
| legitiem: ongemuteerde boom | geen | GROEN |
| legitiem: `Role(` alleen in docstring en comment | extra functie | GROEN |
| legitiem: gewone `Role`-treffers in tests/alembic | buiten scope (`git ls-files src`) | niet gelezen |
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

# Gedateerd 2026-10-04. Sleutel `bestand::functie`, een reden per regel.
ALLOWED_ROLE_CONSTRUCTIONS: dict[str, str] = {
    "src/core/services/rbac_service.py::create_role": (
        "BEWAAKT: controleert is_reserved_role_name(name) VOOR het aanmaken (LOW-1)."
    ),
    "src/core/services/rbac_service.py::ensure_default_roles": (
        "Vaste namen admin/editor/user uit een lijst in de functie zelf, geen invoer van buiten."
    ),
    "src/core/services/rbac_service.py::ensure_platform_role": (
        "Zaait de gereserveerde platformrol als rij voor de gezaaide beheerder (app_lifespan, systeempad); "
        "namen komen uit RESERVED_ROLE_NAMES, nooit uit invoer van buiten -- brief 2026-10-19."
    ),
    "src/ensure_demo_user.py::_zorg_voor_rol_en_gebruiker": (
        "Platformscript dat de vaste rol UserRole.ADMIN voor de demogebruiker zaait; geen klant."
    ),
}

_MODULE = "<module>"


def role_constructions(source: str, path: str) -> set[str]:
    """Alle `bestand::functie`-sleutels waar `Role(...)` wordt aangeroepen."""
    tree = ast.parse(source)
    found: set[str] = set()

    def visit(node: ast.AST, functie: str) -> None:
        if isinstance(node, ast.Call):
            f = node.func
            naam = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            if naam == "Role":
                found.add(f"{path}::{functie}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functie = node.name
        for kind in ast.iter_child_nodes(node):
            visit(kind, functie)

    visit(tree, _MODULE)
    return found


def role_alias_imports(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for a in n.names
        if a.name == "Role" and a.asname not in (None, "Role")
    ]


def _src_files() -> dict[str, str]:
    uit = subprocess.run(
        ["git", "ls-files", "src"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return {p: (_ROOT / p).read_text(encoding="utf-8") for p in uit if p.endswith(".py")}


def scan(bronnen: dict[str, str]) -> set[str]:
    gevonden: set[str] = set()
    for pad, tekst in bronnen.items():
        gevonden |= role_constructions(tekst, pad)
    return gevonden


@pytest.fixture(scope="module")
def bronnen() -> dict[str, str]:
    return _src_files()


# --------------------------------------------------------------------------- de guard zelf


def test_no_unlisted_role_construction_exists_in_src(bronnen: dict[str, str]) -> None:
    nieuw = sorted(scan(bronnen) - set(ALLOWED_ROLE_CONSTRUCTIONS))
    assert nieuw == [], (
        f"Role(...) wordt aangemaakt buiten de uitzonderingslijst: {nieuw}. Ga door "
        "RBACService.create_role (die de gereserveerde rolnaam weigert), of zet de plek met "
        "een reden op ALLOWED_ROLE_CONSTRUCTIONS."
    )


def test_every_allowed_role_construction_still_exists(bronnen: dict[str, str]) -> None:
    verouderd = sorted(set(ALLOWED_ROLE_CONSTRUCTIONS) - scan(bronnen))
    assert verouderd == [], f"Uitzondering bestaat niet meer, haal hem van de lijst: {verouderd}"


def test_every_exception_has_a_reason() -> None:
    assert [k for k, v in ALLOWED_ROLE_CONSTRUCTIONS.items() if len(v.strip()) < 10] == []


def test_role_is_never_imported_under_an_alias(bronnen: dict[str, str]) -> None:
    assert {p: role_alias_imports(t) for p, t in bronnen.items() if role_alias_imports(t)} == {}


def test_there_is_exactly_one_orm_class_named_role(bronnen: dict[str, str]) -> None:
    klassen = [
        pad
        for pad, tekst in bronnen.items()
        for n in ast.walk(ast.parse(tekst))
        if isinstance(n, ast.ClassDef) and n.name == "Role"
    ]
    assert klassen == ["src/core/models/rbac_models.py"]


# --------------------------------------------------------------------------- mutaties (in het geheugen)


def _met_extra_functie(bronnen: dict[str, str], pad: str, naam: str) -> dict[str, str]:
    kopie = dict(bronnen)
    kopie[pad] = bronnen[pad] + f"\n\ndef {naam}(n):\n    return Role(name=n)\n"
    return kopie


def test_mutation_a_role_in_an_unlisted_file_is_caught(bronnen: dict[str, str]) -> None:
    kopie = _met_extra_functie(bronnen, "src/core/api/v1/users/shared.py", "maak_rol")
    assert "src/core/api/v1/users/shared.py::maak_rol" in scan(kopie) - set(
        ALLOWED_ROLE_CONSTRUCTIONS
    )


def test_mutation_a_second_role_in_a_listed_file_is_caught(bronnen: dict[str, str]) -> None:
    kopie = _met_extra_functie(bronnen, "src/core/services/rbac_service.py", "omweg")
    assert "src/core/services/rbac_service.py::omweg" in scan(kopie) - set(
        ALLOWED_ROLE_CONSTRUCTIONS
    )


def test_mutation_a_role_in_a_listed_demo_script_function_elsewhere_is_caught(
    bronnen: dict[str, str],
) -> None:
    kopie = _met_extra_functie(bronnen, "src/ensure_demo_user.py", "omweg")
    assert "src/ensure_demo_user.py::omweg" in scan(kopie) - set(ALLOWED_ROLE_CONSTRUCTIONS)


def test_mutation_a_role_inside_a_nested_function_gets_the_inner_name(
    bronnen: dict[str, str],
) -> None:
    bron = "def buiten():\n    def binnen():\n        return Role(name='x')\n    return binnen\n"
    assert role_constructions(bron, "p.py") == {"p.py::binnen"}


@pytest.mark.parametrize("sleutel", sorted(ALLOWED_ROLE_CONSTRUCTIONS))
def test_mutation_removing_the_role_call_makes_the_exception_stale(
    bronnen: dict[str, str], sleutel: str
) -> None:
    pad, _, functie = sleutel.partition("::")
    tree = ast.parse(bronnen[pad])
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == functie:
            for c in ast.walk(n):
                if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "Role":
                    c.func = ast.Name(id="NietRole", ctx=ast.Load())
    kopie = dict(bronnen)
    kopie[pad] = ast.unparse(tree)
    assert sleutel not in scan(kopie)


def test_a_listed_construction_is_not_flagged(bronnen: dict[str, str]) -> None:
    assert scan(bronnen) - set(ALLOWED_ROLE_CONSTRUCTIONS) == set()


def test_mention_in_docstring_comment_or_select_is_not_a_construction() -> None:
    bron = (
        'def f():\n    """Maakt Role(name=x) aan."""\n    # Role(name=y)\n'
        "    return select(Role).where(Role.id == 1)\n"
    )
    assert role_constructions(bron, "p.py") == set()


def test_an_alias_import_is_detected() -> None:
    assert role_alias_imports("from src.core.models.rbac_models import Role as R") != []


def test_a_plain_role_import_is_not_flagged() -> None:
    assert role_alias_imports("from src.core.models.rbac_models import Role, User") == []


def test_the_scan_is_limited_to_src(bronnen: dict[str, str]) -> None:
    assert [p for p in bronnen if not p.startswith("src/")] == []
