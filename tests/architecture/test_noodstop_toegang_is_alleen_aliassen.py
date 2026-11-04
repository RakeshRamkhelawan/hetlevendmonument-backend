"""De ene ingang `noodstop_toegang.py` is ALLEEN aliassen op de guard (security-hertoets 2026-10-24, aanbeveling 1).

Elke deur van agent_runtime controleert de noodstop via `src/core/services/noodstop_toegang.py`. Dat maakt de
facade de enige plek waar een deur stil van gedrag kan veranderen: een alias die naar een no-op wijst, of een
eigen functie met dezelfde naam, en elke deur laat de stilgezette klant door terwijl alle tekstcontroles groen
blijven. `test_elke_deur_controleert_de_noodstop` toetst alleen de TEKST `"<naam> = guard.<naam>"`; deze test
toetst de IDENTITEIT en de STRUCTUUR.

**Wat hij bewaakt (benoemde verzameling `ALIASSEN`, een mutatie per element):** de vijf namen van de facade.
Elke naam moet hetzelfde OBJECT zijn als dat in `guard` of `metrics`, en de facade mag geen functie of klasse
definieren (dan is er logica, en die hoort in de guard).

MUTATIEBEWIJS (2026-10-24, op een kopie van de facade in een tijdelijke map):
    `eis_klant_actief` als eigen no-op-functie                    -> `..._zijn_hetzelfde_object` ROOD
    `klant_staat_stil` naar een andere functie laten wijzen        -> ROOD
    `NOODSTOP_GEWEIGERD` een eigen teller                          -> ROOD
    een eigen helperfunctie in de facade                           -> `..._definieert_geen_logica` ROOD
    legitiem: een extra alias naar een bestaande guardfunctie      -> beide GROEN
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.core.noodstop import guard, metrics
from src.core.services import noodstop_toegang

ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "src/core/services/noodstop_toegang.py"

#: naam in de facade -> (module, naam daar)
ALIASSEN: dict[str, tuple[object, str]] = {
    "KlantStilgezet": (guard, "KlantStilgezet"),
    "eis_klant_actief": (guard, "eis_klant_actief"),
    "eis_chat_actief": (guard, "eis_chat_actief"),
    "klant_staat_stil": (guard, "klant_staat_stil"),
    "NOODSTOP_GEWEIGERD": (metrics, "NOODSTOP_GEWEIGERD"),
}


def _definities(tekst: str) -> list[str]:
    boom = ast.parse(tekst)
    return [
        k.name
        for k in ast.walk(boom)
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def test_de_aliassen_zijn_hetzelfde_object_als_in_de_guard() -> None:
    afwijkend = [
        naam
        for naam, (module, daar) in ALIASSEN.items()
        if getattr(noodstop_toegang, naam) is not getattr(module, daar)
    ]

    assert afwijkend == []


def test_de_facade_definieert_geen_logica() -> None:
    assert _definities(FACADE.read_text(encoding="utf-8")) == []


def test_een_eigen_functie_in_de_facade_wordt_gezien() -> None:
    tekst = "async def eis_klant_actief(klant: int) -> None:\n    return None\n"

    assert _definities(tekst) == ["eis_klant_actief"]


def test_de_verzameling_aliassen_is_de_publieke_api_van_de_facade() -> None:
    """Een nieuwe publieke naam zonder identiteitscontrole zou hier ongemerkt kunnen ontsnappen."""
    assert set(noodstop_toegang.__all__) == set(ALIASSEN)
