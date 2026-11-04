"""De websocketlaag kiest nooit een standaardtenant (acceptant scenario 5, 2026-10-05).

**De bevinding.** `ConnectionManager.connect` deed `int(payload.get("tenant_id", 1))`, en
`ChannelConnection.tenant_id` stond standaard op `1`. Een geldig token zonder `tenant_id`, of een
verbinding zonder token, hoorde zo bij tenant 1 en kreeg diens `broadcast_to_tenant` te zien. Nu
weigert `connect` zo'n token met 1008 en hoort een verbinding zonder token bij geen tenant
(`tests/unit/websocket/test_geen_standaardtenant.py`).

**De verzameling die deze guard bewaakt:** elk bestand onder `src/` dat `WebSocket` importeert of
in `src/core/websocket/` staat (de websocketlaag). Daarin drie vormen van een terugval op een vaste
tenant, elk als STRUCTUUR (`ast`), niet als tekst:

1. `<x>.get("tenant_id", <getal>)` -- de oorspronkelijke vorm.
2. `<iets met tenant_id> or <getal>` -- dezelfde terugval anders geschreven.
3. `tenant_id = <getal>` / `tenant_id: int = <getal>` -- een vaste waarde als begin- of standaardwaarde,
   als naam, attribuut of dataclassveld.

**Mutatiebewijs (2026-10-05, harnas `.probe/mutate.py`, per mutatie een kopie):**

- Voorwaarts 1: in `manager.py` `_tenant_uit_token(payload)` vervangen door
  `int(payload.get("tenant_id", 1))` -> ROOD.
- Voorwaarts 2: in `manager.py` `payload.get("tenant_id") or 1` -> ROOD.
- Voorwaarts 3a: dataclassveld `tenant_id: int | None = None` -> `tenant_id: int = 1` -> ROOD.
- Voorwaarts 3b: in `connect` `tenant_id: int | None = None` -> `tenant_id: int = 1` -> ROOD.
- Voorwaarts 4: in een endpointbestand (`api/v1/websocket_hitl.py`) `conn.tenant_id = 1` -> ROOD.
- Achterwaarts: `payload.get("tenant_id")` zonder standaard, `tenant_id: int | None = None` en
  `int(payload["tenant_id"])` blijven GROEN; en `get("tenant_id", 1)` in een bestand BUITEN de
  websocketlaag (`agents/workflow_engine.py`, staat er al) laat deze guard groen -- hij is niet
  voor de hele codebase.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
WEBSOCKETLAAG = SRC / "core" / "websocket"


def _is_websocketbestand(pad: Path, boom: ast.Module) -> bool:
    if WEBSOCKETLAAG in pad.parents:
        return True
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom) and any(a.name == "WebSocket" for a in knoop.names):
            return True
    return False


def _noemt_tenant(knoop: ast.AST) -> bool:
    for k in ast.walk(knoop):
        if isinstance(k, ast.Name) and k.id == "tenant_id":
            return True
        if isinstance(k, ast.Attribute) and k.attr == "tenant_id":
            return True
        if isinstance(k, ast.Constant) and k.value == "tenant_id":
            return True
    return False


def _is_getal(knoop: ast.AST | None) -> bool:
    return (
        isinstance(knoop, ast.Constant)
        and isinstance(knoop.value, int)
        and not isinstance(knoop.value, bool)
    )


def _is_tenantdoel(doel: ast.AST) -> bool:
    return (isinstance(doel, ast.Name) and doel.id == "tenant_id") or (
        isinstance(doel, ast.Attribute) and doel.attr == "tenant_id"
    )


def _terugvallen(boom: ast.Module) -> list[tuple[int, str]]:
    gevonden: list[tuple[int, str]] = []
    for k in ast.walk(boom):
        if (
            isinstance(k, ast.Call)
            and isinstance(k.func, ast.Attribute)
            and k.func.attr == "get"
            and len(k.args) == 2
            and isinstance(k.args[0], ast.Constant)
            and k.args[0].value == "tenant_id"
            and _is_getal(k.args[1])
        ):
            gevonden.append((k.lineno, 'get("tenant_id", <getal>)'))
        elif (
            isinstance(k, ast.BoolOp)
            and isinstance(k.op, ast.Or)
            and _is_getal(k.values[-1])
            and any(_noemt_tenant(v) for v in k.values[:-1])
        ):
            gevonden.append((k.lineno, "tenant_id or <getal>"))
        elif isinstance(k, ast.Assign) and _is_getal(k.value) and any(map(_is_tenantdoel, k.targets)):
            gevonden.append((k.lineno, "tenant_id = <getal>"))
        elif isinstance(k, ast.AnnAssign) and _is_getal(k.value) and _is_tenantdoel(k.target):
            gevonden.append((k.lineno, "tenant_id: ... = <getal>"))
    return gevonden


def _websocketlaag() -> list[tuple[Path, ast.Module]]:
    bestanden: list[tuple[Path, ast.Module]] = []
    for pad in SRC.rglob("*.py"):
        if "activepieces" in pad.parts:
            continue
        boom = ast.parse(pad.read_text(encoding="utf-8"), filename=str(pad))
        if _is_websocketbestand(pad, boom):
            bestanden.append((pad, boom))
    return bestanden


def test_de_websocketlaag_is_gevonden() -> None:
    """Zonder dit kan de guard groen zijn omdat hij niets ziet."""
    namen = {p.relative_to(SRC).as_posix() for p, _ in _websocketlaag()}
    assert {"core/websocket/manager.py", "core/api/v1/websocket_hitl.py"} <= namen


def test_de_websocketlaag_valt_nooit_terug_op_een_vaste_tenant() -> None:
    fouten = [
        f"{pad.relative_to(REPO_ROOT).as_posix()}:{regel}: {vorm}"
        for pad, boom in _websocketlaag()
        for regel, vorm in _terugvallen(boom)
    ]
    assert not fouten, (
        "De websocketlaag kiest een vaste tenant als de echte ontbreekt. Weiger in plaats "
        "daarvan (websocket.close(code=1008)) of laat de verbinding bij geen tenant horen "
        f"(None): {fouten}"
    )
