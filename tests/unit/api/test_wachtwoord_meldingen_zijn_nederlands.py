"""De meldingen bij wachtwoord wijzigen en herstellen zijn Nederlands (studio deel 2, punt 5).

De API antwoordde Engels ("User not found", "Current password is incorrect", "Invalid or expired token"), terwijl het scherm
Nederlands toont. De teksten staan nu als benoemde constanten bovenaan de module en elke melding verwijst daarnaar: een nieuwe
Engelse tekst zonder constante valt direct op in `test_elke_melding_komt_uit_een_benoemde_constante`.

De drie "token ongeldig"-plekken in `reset_password` geven BEWUST dezelfde tekst: een ander antwoord zou verraden of een token
nooit bestond, of verlopen is, of bij een verdwenen gebruiker hoort.

Mutatiebewijs (2026-10-28): een melding terug op een Engelse letterlijke tekst: `test_elke_melding_komt_uit_een_benoemde_constante`
rood; de tekst van een constante op Engels: `test_de_meldingen_hebben_de_afgesproken_nederlandse_tekst` rood; een van de drie
tokenmeldingen op een eigen tekst: `test_alle_tokenmeldingen_zijn_dezelfde_constante` rood. De andere kant op: de constanten
bestaan allemaal en worden gebruikt (`test_elke_constante_wordt_gebruikt`), anders is "alles weghalen" een oplossing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.api.auth import router_password

VERWACHT = {
    "GEBRUIKER_NIET_GEVONDEN": "Gebruiker niet gevonden",
    "HUIDIG_WACHTWOORD_FOUT": "Het huidige wachtwoord klopt niet",
    "WACHTWOORD_GEWIJZIGD": "Uw wachtwoord is gewijzigd",
    "HERSTELLINK_ONGELDIG": "Deze herstellink is ongeldig of verlopen",
    "WACHTWOORD_HERSTELD": "Uw wachtwoord is hersteld",
    "HERSTEL_MISLUKT": "Het wachtwoord kon niet worden hersteld. Probeer het opnieuw.",
}


def _module() -> ast.Module:
    return ast.parse(Path(router_password.__file__).read_text(encoding="utf-8"))


def _meldingen() -> list[tuple[int, ast.expr]]:
    """Elke tekst die een medewerker te zien kan krijgen: `detail=` van een HTTPException, `{"message": ...}` en een
    teruggegeven constante. De definities van de constanten bovenaan de module tellen niet mee: daar staat de tekst bewust."""
    boom = _module()
    definities = {
        id(w)
        for n in boom.body
        if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None
        for w in ast.walk(n.value)
    }
    gevonden: list[tuple[int, ast.expr]] = []
    for node in ast.walk(boom):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException":
            gevonden += [(k.value.lineno, k.value) for k in node.keywords if k.arg == "detail"]
        if isinstance(node, ast.Dict) and id(node) not in definities:
            for sleutel, waarde in zip(node.keys, node.values):
                if isinstance(sleutel, ast.Constant) and sleutel.value == "message":
                    gevonden.append((waarde.lineno, waarde))
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            gevonden.append((node.lineno, node.value))
    return gevonden


def _tekst(waarde: object) -> str:
    return str(waarde["message"] if isinstance(waarde, dict) else waarde)


@pytest.mark.unit
def test_er_zijn_meldingen_om_te_toetsen() -> None:
    assert len(_meldingen()) >= 10


@pytest.mark.unit
def test_elke_melding_komt_uit_een_benoemde_constante() -> None:
    letterlijk = [
        f"regel {regel}" for regel, waarde in _meldingen() if not isinstance(waarde, ast.Name)
    ]

    assert letterlijk == []


@pytest.mark.unit
@pytest.mark.parametrize("naam", sorted(VERWACHT))
def test_de_meldingen_hebben_de_afgesproken_nederlandse_tekst(naam: str) -> None:
    assert _tekst(getattr(router_password, naam)) == VERWACHT[naam]


@pytest.mark.unit
def test_alle_tokenmeldingen_zijn_dezelfde_constante() -> None:
    aantal = sum(
        1
        for _, waarde in _meldingen()
        if isinstance(waarde, ast.Name) and waarde.id == "HERSTELLINK_ONGELDIG"
    )

    assert aantal == 3


@pytest.mark.unit
@pytest.mark.parametrize("naam", sorted(VERWACHT))
def test_elke_constante_wordt_gebruikt(naam: str) -> None:
    gebruikt = {waarde.id for _, waarde in _meldingen() if isinstance(waarde, ast.Name)}

    assert naam in gebruikt


@pytest.mark.unit
def test_geen_enkele_melding_bevat_een_oude_engelse_tekst() -> None:
    engels = ("not found", "incorrect", "Invalid", "successfully", "An error")
    teksten = [_tekst(getattr(router_password, naam)) for naam in VERWACHT]

    assert [t for t in teksten if any(woord in t for woord in engels)] == []
