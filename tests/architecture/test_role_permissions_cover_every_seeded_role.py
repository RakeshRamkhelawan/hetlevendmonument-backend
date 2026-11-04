"""Elke gezaaide rol heeft de toolrechten die hij hoort te hebben, in de DATABASE (ADR-036 OP-143).

Sinds OP-143 (2026-10-09) beslist `role_permissions` of een agent een tool mag draaien namens
een gebruiker: `RBACService.user_has_scope_for` vraagt de database, dezelfde bron als de
HTTP-routes. De vaste matrix in `auth/rbac.py` bestaat niet meer. Een rol die
`ensure_default_roles` zaait zonder de juiste rij krijgt dus nul toegang, en een rij die er te
veel staat verruimt rechten stilzwijgend.

**Wat deze guard toetst, per rol en per toolrecht.** De verwachting staat hieronder als
benoemde tabel (`VERWACHT`). De guard leest de zaailijst STRUCTUREEL (AST van de
`defaults`-toekenning in `ensure_default_roles`), rekent met dezelfde jokerregel als
`RBACService.user_has_permission` (resource en actie matchen letterlijk of via `*`) en vergelijkt
voor elke rol en voor elk recht in `TOOL_RECHTEN` het antwoord met de tabel. Zo wordt zowel een
ontbrekende rij (rol krijgt te weinig) als een extra rij (rol krijgt te veel) betrapt.

**De uitzondering voor `editor` is weg.** Tot OP-143 stond `editor` hier als bekende uitzondering
(gezaaid, maar niet in de matrix, dus `MISSING_SCOPE` op elke tool). Hij krijgt nu `tools:read`:
de enige bewuste verruiming van die wijziging.

**Waarom de bron via een AST-parse wordt gelezen en niet geimporteerd.** De standaardlijst is een
lokale variabele binnen `ensure_default_roles`. Een tekstzoektocht zou een naam in een toelichting
meetellen; `test_de_bron_is_echt_gelezen` faalt als de parse niets oplevert.

**Mutatiebewijs:** zie de docstring van `test_the_seeded_rights_match_the_table`.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from src.core.auth.rbac import TOOL_RECHTEN

_REPO = Path(__file__).resolve().parents[2]
_RBAC_SERVICE = _REPO / "src/core/services/rbac_service.py"

#: Per gezaaide rol: welke rechten uit `TOOL_RECHTEN` hij heeft. Gedateerd 2026-10-09, besluit
#: van OP-143. `admin` heeft ze allemaal via `*:*`; `editor` heeft alleen lezen.
VERWACHT: dict[str, frozenset[str]] = {
    "admin": frozenset(
        {
            "tools:read",
            "tools:write",
            "tools:admin",
            "receivables:propose",
            "hr:read",
            "tasks:write",
            "payables:write",
        }
    ),
    "user": frozenset({"tools:read"}),
    "debiteuren": frozenset({"tools:read", "receivables:propose"}),
    # Crediteuren dag 2 (2026-10-24): de crediteurenagent heeft tools (`record_supplier_invoice`, `propose_supplier_invoice`)
    # die `payables:write` vragen; de rol heeft dat recht al sinds dag 1 en geen `tools:read` (de agent heeft geen leestools).
    "crediteuren": frozenset({"payables:write"}),
    # 2026-10-23 (besluit Rakesh "ja"): een medewerker die workflows bouwt mag via een workflowstap taken aanmaken en
    # wijzigen, met het smalle recht `tasks:write` en NIET met `tools:write` (dat opent elke schrijftool).
    "editor": frozenset({"tools:read", "tasks:write"}),
    # ADR-039 (2026-10-09): goedkeuren is een procesbevoegdheid; `receivables:approve` zit niet in
    # TOOL_RECHTEN, dus alleen het leesrecht voor tools telt hier.
    "goedkeurder": frozenset({"tools:read"}),
    # De goedkeurder personeel moet het voorstel kunnen zien dat hij beslist (HR-pilot dag 2).
    "goedkeurder_hr": frozenset({"tools:read", "hr:read"}),
    # HR-pilot dag 1 (2026-10-10): personeelsgegevens lezen en de kloofanalyse draaien, geen beheerder.
    "hr_medewerker": frozenset({"tools:read", "hr:read"}),
}


def _gezaaide_rijen() -> dict[str, frozenset[tuple[str, str]]]:
    """Per rolnaam de (resource, actie)-rijen die `ensure_default_roles` zaait."""
    boom = ast.parse(_RBAC_SERVICE.read_text(encoding="utf-8"))
    rollen: dict[str, frozenset[tuple[str, str]]] = {}
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "defaults" for t in knoop.targets):
            continue
        if not isinstance(knoop.value, ast.List):
            continue
        for element in knoop.value.elts:
            if not (isinstance(element, ast.Tuple) and len(element.elts) == 3):
                continue
            naam, _, rechten = element.elts
            if not (isinstance(naam, ast.Constant) and isinstance(naam.value, str)):
                continue
            rijen: list[tuple[str, str]] = []
            if isinstance(rechten, ast.List):
                for item in rechten.elts:
                    if isinstance(item, ast.Dict):
                        sleutels = {
                            k.value: v.value
                            for k, v in zip(item.keys, item.values, strict=True)
                            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                        }
                        rijen.append((str(sleutels.get("resource")), str(sleutels.get("action"))))
            rollen[naam.value.strip().lower()] = frozenset(rijen)
    return rollen


def _heeft(rijen: frozenset[tuple[str, str]], recht: str) -> bool:
    """Dezelfde jokerregel als `RBACService.user_has_permission`."""
    resource, _, actie = recht.partition(":")
    return any(r in (resource, "*") and a in (actie, "*") for r, a in rijen)


def test_de_bron_is_echt_gelezen() -> None:
    """Vangnet: een parse die niets oplevert maakt de tests hieronder trivially groen."""
    rollen = _gezaaide_rijen()

    assert len(rollen) >= 4 and all(rollen.values()), (
        f"Uit {_RBAC_SERVICE} zijn {len(rollen)} rollen gelezen ({sorted(rollen)}), sommige "
        "zonder rijen. De `defaults`-lijst is hernoemd of verplaatst; deze guard meet niets meer."
    )


def test_every_seeded_role_is_declared_in_the_table() -> None:
    """Een nieuwe gezaaide rol MOET hier zijn toolrechten benoemen, ook als dat er nul zijn."""
    onbenoemd = sorted(_gezaaide_rijen().keys() - VERWACHT.keys())

    assert not onbenoemd, (
        f"Deze rollen worden door `ensure_default_roles` gezaaid maar staan niet in VERWACHT: "
        f"{onbenoemd}. Zonder regel is niet vastgelegd welke tools de rol hoort te mogen."
    )


def test_the_table_is_not_stale() -> None:
    """Een rol in de tabel die niet meer wordt gezaaid MOET eruit -- anders rot hij dicht."""
    verouderd = sorted(VERWACHT.keys() - _gezaaide_rijen().keys())

    assert not verouderd, f"Deze rollen in VERWACHT worden niet meer gezaaid: {verouderd}."


@pytest.mark.parametrize("rol", sorted(VERWACHT))
def test_the_seeded_rights_match_the_table(rol: str) -> None:
    """Per rol: voor elk recht in `TOOL_RECHTEN` klopt het antwoord met de tabel.

    **Mutatiebewijs (2026-10-09), op een kopie van `rbac_service.py`, een regel per rol en per
    richting:** `tools:read` bij `editor` weggehaald -> ROOD (`editor`); een rij
    `tools:write` bij `user` toegevoegd -> ROOD (`user`); `receivables:propose` bij `debiteuren`
    weggehaald -> ROOD (`debiteuren`); `*:*` bij `admin` vervangen door `*:read` -> ROOD (`admin`).
    Een bestand in `src` met de naam van de vaste matrix als `Name` of attribuut -> ROOD
    (`test_the_role_matrix_is_gone_from_src`); dezelfde naam alleen in een commentaar of een
    tekenreeks -> GROEN. Ongewijzigd -> GROEN voor alle vier de rollen.
    """
    rijen = _gezaaide_rijen().get(rol, frozenset())
    krijgt = frozenset(recht for recht in TOOL_RECHTEN if _heeft(rijen, recht))

    assert krijgt == VERWACHT[rol], (
        f"rol {rol!r}: zaailijst geeft {sorted(krijgt)}, verwacht {sorted(VERWACHT[rol])}. "
        f"Te weinig: {sorted(VERWACHT[rol] - krijgt)}; te veel: {sorted(krijgt - VERWACHT[rol])}."
    )


def test_the_rights_check_is_not_vacuous() -> None:
    """De tweede richting: de jokerregel zelf wordt gemeten, anders is 'iedereen alles' groen."""
    assert (
        _heeft(frozenset({("*", "*")}), "tools:admin"),
        _heeft(frozenset({("tools", "read")}), "tools:write"),
        _heeft(frozenset({("*", "read")}), "tools:read"),
        _heeft(frozenset({("agents", "*")}), "tools:read"),
    ) == (True, False, True, False)


def test_the_role_matrix_is_gone_from_src() -> None:
    """De vaste rolmatrix naast de database komt in `src` niet meer voor.

    Structureel: een `Name`-knoop of attribuut met die naam, over alle bestanden onder `src`
    (`git ls-files`, dus ook nieuwe bestanden). Een toelichting die de naam noemt telt niet mee.
    """
    naam_van_de_matrix = "ROLE_" + "PERMISSIONS"
    uitvoer = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "src"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    treffers: list[str] = []
    for pad in sorted(p for p in uitvoer if p.endswith(".py")):
        bestand = _REPO / pad
        if not bestand.is_file():
            continue
        for knoop in ast.walk(ast.parse(bestand.read_text(encoding="utf-8"))):
            if (isinstance(knoop, ast.Name) and knoop.id == naam_van_de_matrix) or (
                isinstance(knoop, ast.Attribute) and knoop.attr == naam_van_de_matrix
            ):
                treffers.append(f"{pad}:{knoop.lineno}")

    assert not treffers, (
        f"De vaste rolmatrix komt weer voor in src: {treffers}. Rechten staan in "
        "`role_permissions` (OP-143); een tweede bron in de code is het probleem dat dit sloot."
    )
