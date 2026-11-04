"""De noodstopcontrole van de focus-builder-websocket komt uit `focus_builder/dependencies.py` (ADR-033).

De DSM-meter telt voor core_api het aantal unieke bestand->bak-paren. `ws_chat_router.py` importeerde
`src.core.noodstop.guard` zelf: dat was een eigen paar naar `infra`. Een router hoort alleen te gebruiken wat
`dependencies.py` van zijn domein aanbiedt; daar staat de noodstopcontrole nu, naast de andere re-exports. Het
gedrag blijft gelijk: elk modelbericht roept `eis_chat_actief(user.tenant_id)` aan en een stop geeft de vaste
melding met code NOODSTOP, fail-closed (de deurtest `test_elke_deur_controleert_de_noodstop` bewaakt dat).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

ROOT = Path(__file__).resolve().parents[2]
FB = ROOT / "src" / "core" / "api" / "v1" / "focus_builder"
ROUTER = FB / "ws_chat_router.py"
DEPENDENCIES = FB / "dependencies.py"
GUARD = "src.core.services.noodstop_toegang"
NAMEN = {"KlantStilgezet", "eis_chat_actief"}


def _imports(pad: Path) -> list[ast.ImportFrom]:
    return [
        n
        for n in ast.walk(ast.parse(pad.read_text(encoding="utf-8")))
        if isinstance(n, ast.ImportFrom) and n.level == 0
    ]


def _namen_uit(pad: Path, module: str) -> set[str]:
    return {a.name for n in _imports(pad) if n.module == module for a in n.names}


def test_de_router_importeert_niets_uit_de_noodstop() -> None:
    rechtstreeks = [n.module for n in _imports(ROUTER) if (n.module or "").startswith("src.core.noodstop")]
    assert not rechtstreeks, (
        "ws_chat_router.py importeert zelf uit de noodstop; dat is een eigen DSM-paar naar infra. "
        f"Laat de router de namen uit focus_builder/dependencies.py halen (ADR-033): {rechtstreeks}"
    )


def test_dependencies_biedt_de_noodstopcontrole_aan() -> None:
    assert NAMEN <= _namen_uit(DEPENDENCIES, GUARD), "dependencies.py importeert de controle niet uit de ingang (noodstop_toegang)"
    boom = ast.parse(DEPENDENCIES.read_text(encoding="utf-8"))
    alle: set[str] = set()
    for n in boom.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets):
            alle = {e.value for e in ast.walk(n.value) if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    assert NAMEN <= alle, "de noodstopnamen staan niet in `__all__` van focus_builder/dependencies.py"


def test_de_router_gebruikt_de_controle_uit_dependencies() -> None:
    bron = ROUTER.read_text(encoding="utf-8")
    assert NAMEN <= _namen_uit(ROUTER, "src.core.api.v1.focus_builder.dependencies")
    # De controle zelf staat er nog, en vlak voor een modelbericht (zie ook de deurtest).
    assert "await eis_chat_actief(user.tenant_id)" in bron
    assert "except KlantStilgezet" in bron
