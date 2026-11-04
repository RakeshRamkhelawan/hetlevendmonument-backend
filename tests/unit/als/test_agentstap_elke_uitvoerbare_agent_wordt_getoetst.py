"""Elke agent die een agentstap kan uitvoeren wordt op het recht van de starter getoetst (Gate 2, agentstap dag 1).

Een agent komt op twee manieren langs de startertoets: via `act()` (elke tool gaat dan per stuk door
`starter_heeft_toolrecht`), of -- als hij zelf gegevens leest en `act()` niet aanroept -- via het leesrecht in
`EIGEN_LEESRECHT` (`src/core/als/agents/workflow_stap.py`). Een derde manier bestaat niet: een agent in
`UITVOERBARE_AGENT_SLEUTELS` die geen van beide doet, geeft elke gebruiker die een workflow mag starten zijn
gegevens (gevonden door de security-review: `vatcompliance` en `receiptscanner`).

Mutatiebewijs (2026-10-24): `vatcompliance` uit `EIGEN_LEESRECHT` gehaald -> `test_elke_uitvoerbare_agent_...` ROOD met
de naam in de melding. Legitiem: `dunning` roept `act()` aan en staat NIET in de lijst -> groen; een agent in de lijst
die `act()` ook aanroept blijft eveneens groen (de lijst mag meer toetsen, niet minder).
"""

from __future__ import annotations

import ast
from pathlib import Path

WORTEL = Path(__file__).resolve().parents[3]
SKILLS = WORTEL / "src" / "core" / "als" / "agents" / "skills"


def roept_act_aan(bron: str) -> bool:
    """Roept `execute_with_manifest_prompt` van deze skill `self.act(...)` aan (ook in een geneste functie)?"""
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.AsyncFunctionDef) and knoop.name == "execute_with_manifest_prompt":
            for aanroep in ast.walk(knoop):
                if (
                    isinstance(aanroep, ast.Call)
                    and isinstance(aanroep.func, ast.Attribute)
                    and aanroep.func.attr == "act"
                    and isinstance(aanroep.func.value, ast.Name)
                    and aanroep.func.value.id == "self"
                ):
                    return True
    return False


def zonder_toets(
    sleutels: frozenset[str], eigen: dict[str, tuple[str, str]], skills: Path
) -> list[str]:
    """De agents die noch `act()` aanroepen noch een eigen leesrecht hebben."""
    return sorted(
        s
        for s in sleutels
        if s not in eigen and not roept_act_aan((skills / f"{s}.py").read_text(encoding="utf-8"))
    )


def test_elke_uitvoerbare_agent_wordt_getoetst() -> None:
    from src.core.als.agents.workflow_stap import EIGEN_LEESRECHT
    from src.core.als.enterprise.packs import UITVOERBARE_AGENT_SLEUTELS

    assert zonder_toets(UITVOERBARE_AGENT_SLEUTELS, EIGEN_LEESRECHT, SKILLS) == [], (
        "Deze agents in een workflowstap worden NIET op het recht van de starter getoetst: ze roepen `act()` niet aan "
        "(dus geen toolcontrole) en hebben geen eigen leesrecht in EIGEN_LEESRECHT."
    )


def test_de_meting_ziet_het_verschil_tussen_een_agent_met_en_zonder_act() -> None:
    """Zonder deze helft is 'geen enkele agent mist de toets' ook waar als de meting niets ziet."""
    kop = "class S:\n    async def execute_with_manifest_prompt(self, p):\n"
    assert (
        roept_act_aan(kop + "        return await self.act('x')\n"),
        roept_act_aan(kop + "        return 1\n"),
    ) == (
        True,
        False,
    )


def test_een_agent_zonder_act_en_zonder_eigen_recht_wordt_gevonden(tmp_path: Path) -> None:
    (tmp_path / "blootleg.py").write_text(
        "class S:\n    async def execute_with_manifest_prompt(self, p):\n        return 1\n",
        encoding="utf-8",
    )
    assert zonder_toets(frozenset({"blootleg"}), {}, tmp_path) == ["blootleg"]


def test_een_agent_zonder_act_met_een_eigen_recht_is_toegestaan(tmp_path: Path) -> None:
    (tmp_path / "leest.py").write_text(
        "class S:\n    async def execute_with_manifest_prompt(self, p):\n        return 1\n",
        encoding="utf-8",
    )
    assert zonder_toets(frozenset({"leest"}), {"leest": ("receipts", "read")}, tmp_path) == []


def test_de_gelezen_skillbestanden_bestaan() -> None:
    from src.core.als.enterprise.packs import UITVOERBARE_AGENT_SLEUTELS

    assert all((SKILLS / f"{s}.py").is_file() for s in UITVOERBARE_AGENT_SLEUTELS)
