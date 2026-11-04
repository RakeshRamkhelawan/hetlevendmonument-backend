"""De Dramatiq-actor `purge_user_data` roept `_run_purge_en_controleer` aan, niet `_run_purge`.

Zonder die controle ziet Dramatiq een geslaagde taak als een deelstap van de purge mislukte, en
blijven persoonsgegevens staan met alleen een WARNING als signaal. De retry-tests toetsen alleen de
controlerende functie; deze test bewaakt de BEDRADING (AST, dus ook zonder dramatiq in de omgeving).

Mutatiebewijs: zie het verslag (actor weer `_run_purge(...)` laten aanroepen in een kopie -> rood;
huidig bestand -> groen; de scanner-test hieronder bewijst dat een kale aanroep wordt gezien).
"""

from __future__ import annotations

import ast
from pathlib import Path

PAD = Path(__file__).resolve().parents[2] / "src" / "core" / "actors" / "gdpr_purge.py"


def _aangeroepen_namen(bron: str, functienaam: str) -> set[str]:
    boom = ast.parse(bron)
    namen: set[str] = set()
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.AsyncFunctionDef) and knoop.name == functienaam:
            for aanroep in ast.walk(knoop):
                if isinstance(aanroep, ast.Call) and isinstance(aanroep.func, ast.Name):
                    namen.add(aanroep.func.id)
    return namen


def test_de_actor_roept_de_controlerende_functie_aan() -> None:
    namen = _aangeroepen_namen(PAD.read_text(encoding="utf-8"), "purge_user_data")

    assert "_run_purge_en_controleer" in namen


def test_de_actor_roept_de_kale_purge_niet_rechtstreeks_aan() -> None:
    namen = _aangeroepen_namen(PAD.read_text(encoding="utf-8"), "purge_user_data")

    assert "_run_purge" not in namen


def test_de_scanner_ziet_een_actor_die_de_kale_purge_aanroept() -> None:
    bron = "async def purge_user_data(a):\n    return await _run_purge(a)\n"

    assert _aangeroepen_namen(bron, "purge_user_data") == {"_run_purge"}
