"""Geen `text()` met een f-string, `%`-opmaak of `.format` in `src/` (plan nazorg, deel I punt c).

De verdediging tegen SQL-injectie is de ORM met gebonden parameters (OWASP: "prepared
statements"), niet een scan van de body in de middleware. Die verdediging werkt alleen als
niemand waarden in de SQL-tekst zelf plakt. Deze guard bewaakt dat voor `text(...)` en
`sqlalchemy.text(...)`.

Uitzonderingen:
- `src/alembic/versions/`: migraties bouwen DDL met namen van tabellen en policies uit de code
  zelf (geen invoer), en een migratie wijzigen is een eigen interlock.
- `TOEGESTAAN`: per bestand het aantal treffers, met de reden. Het aantal mag niet stijgen; een
  nieuw geval in een bestand op de lijst wordt dus ook rood.

Gemeten 2026-10-08: 97 treffers, waarvan 85 in migraties. Vier gerepareerd (SET LOCAL met de
tenant in twee learning-modules, een INTERVAL in memory_retrieval_service); de rest staat
hieronder.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
MIGRATIES = SRC / "alembic" / "versions"

TOEGESTAAN: dict[str, tuple[int, str]] = {
    "src/core/database/seed.py": (
        2,
        "kolomnamen uit een vaste allowlist in de functie, waarden als :parameters",
    ),
    "src/core/database/unit_of_work.py": (
        3,
        "SAVEPOINT-naam; standaard een interne teller. Een savepointnaam kan niet gebonden "
        "worden in SQL",
    ),
    "src/core/security/data_integrity.py": (
        1,
        "tabelnaam via get_sql_validator() gevalideerd, tenant_id als :parameter",
    ),
    "src/core/services/conversation_persistence.py": (
        2,
        "alleen vaste WHERE-fragmenten uit de code, waarden als :parameters",
    ),
}


def _soort(arg: ast.expr) -> str | None:
    if isinstance(arg, ast.JoinedStr) and any(
        isinstance(v, ast.FormattedValue) for v in arg.values
    ):
        return "f-string"
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
        return "%-opmaak"
    if (
        isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "format"
    ):
        return ".format"
    return None


def _is_text_aanroep(knoop: ast.Call) -> bool:
    func = knoop.func
    if isinstance(func, ast.Name):
        return func.id == "text"
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "text"
        and isinstance(func.value, ast.Name)
        and func.value.id in {"sa", "sqlalchemy"}
    )


def treffers_in(bron: str) -> list[tuple[int, str]]:
    uit: list[tuple[int, str]] = []
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.Call) and _is_text_aanroep(knoop) and knoop.args:
            soort = _soort(knoop.args[0])
            if soort:
                uit.append((knoop.lineno, soort))
    return uit


def _alle_treffers() -> Counter[str]:
    tel: Counter[str] = Counter()
    for pad in SRC.rglob("*.py"):
        if MIGRATIES in pad.parents:
            continue
        try:
            bron = pad.read_text(encoding="utf-8-sig")
            gevonden = treffers_in(bron)
        except SyntaxError:
            continue
        if gevonden:
            tel[pad.relative_to(REPO).as_posix()] += len(gevonden)
    return tel


def test_geen_text_met_interpolatie_buiten_de_uitzonderingen() -> None:
    fout = sorted(
        f"{pad}: {aantal} (toegestaan {TOEGESTAAN.get(pad, (0, ''))[0]})"
        for pad, aantal in _alle_treffers().items()
        if aantal > TOEGESTAAN.get(pad, (0, ""))[0]
    )
    assert not fout, (
        "text() met een f-string, %-opmaak of .format: gebruik een :parameter. " + "; ".join(fout)
    )


def test_uitzonderingen_zijn_niet_stale() -> None:
    tel = _alle_treffers()
    te_ruim = sorted(f"{p}: {tel.get(p, 0)} < {n}" for p, (n, _) in TOEGESTAAN.items() if tel.get(p, 0) < n)
    assert not te_ruim, f"verlaag of verwijder de uitzondering: {te_ruim}"


def test_herkenner_ziet_de_drie_vormen_en_negeert_een_parameter() -> None:
    bron = (
        "text(f'SELECT {x}')\n"
        "text('SELECT %s' % x)\n"
        "text('SELECT {}'.format(x))\n"
        "sa.text(f'DROP {x}')\n"
        "text('SELECT :x')\n"
        "text(f'SELECT 1')\n"
    )
    assert [s for _, s in treffers_in(bron)] == ["f-string", "%-opmaak", ".format", "f-string"]
