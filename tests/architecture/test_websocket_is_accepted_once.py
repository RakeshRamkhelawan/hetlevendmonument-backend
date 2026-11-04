"""Een websocket wordt precies EEN keer geaccepteerd (meetlat-scenario 5, 2026-10-05).

`get_ws_user` en `WebSocketAuthenticator.authenticate` accepteren de socket al. Een endpoint
dat daarna nog eens `accept()` aanroept -- direct, of via een `<manager>.connect()` die
onvoorwaardelijk accepteert -- krijgt van Starlette
`RuntimeError: Expected ASGI message "websocket.send" or "websocket.close", but got
'websocket.accept'`. De HITL-pagina bleef daardoor op "Offline".

Wat telt als "al geaccepteerd": een parameter met `Depends(get_ws_user)`, of een aanroep
`<x>.authenticate(...)` (NIET `authenticate_connected_user`, die verwacht juist een al
geaccepteerde socket). Een `accept()` is veilig als hij in een `if` staat waarvan de test
`client_state` vergelijkt met `WebSocketState.CONNECTING`.

Mutatiebewijs (2026-10-05, kopie als terugweg):
- Voorwaarts 1: de `if client_state == CONNECTING` in `src/core/websocket/manager.py::connect`
  weggehaald -> rood op `websocket_hitl.py::websocket_hitl_endpoint`.
- Voorwaarts 2: in `src/core/api/v1/agentic/websocket.py::agent_stream_websocket` de
  `await websocket.accept()` teruggezet -> rood.
- Voorwaarts 3: de guard in `swarm_websocket_endpoints.py::SwarmConnectionManager.connect`
  weggehaald -> rood op `swarm_stream` en `swarm_stream_secure`.
- Achterwaarts: `monitoring_v1/dashboard_router.py` (onvoorwaardelijke accept in zijn eigen
  `connect`, maar het endpoint authenticeert via HTTP-dependencies en accepteert niet vooraf)
  blijft groen; `agentic_flow_endpoints.py` (accept, daarna `authenticate_connected_user`)
  blijft groen.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def _is_guarded_accept_test(test: ast.expr) -> bool:
    names = {n.attr for n in ast.walk(test) if isinstance(n, ast.Attribute)}
    return "client_state" in names and "CONNECTING" in names


def _unguarded_accepts(func: ast.AST) -> list[int]:
    """Regelnummers van `<x>.accept()` die NIET onder een CONNECTING-check staan."""
    found: list[int] = []

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.If):
            inner = guarded or _is_guarded_accept_test(node.test)
            for child in node.body:
                visit(child, inner)
            for child in node.orelse:
                visit(child, guarded)
            return
        if node is not func and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "accept"
            and not node.args
            and not guarded
        ):
            found.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(func, False)
    return found


def _accepting_connect_classes(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "connect"
                    and _unguarded_accepts(item)
                ):
                    out.add(node.name)
    return out


def _instances(tree: ast.Module, classes: set[str]) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in classes
        ):
            out.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return out


def _central_manager_accepts() -> bool:
    tree = ast.parse((SRC / "core/websocket/manager.py").read_text(encoding="utf-8"))
    return "ConnectionManager" in _accepting_connect_classes(tree)


def _imports_central_manager(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.core.websocket.manager":
            for alias in node.names:
                if alias.name == "connection_manager":
                    out.add(alias.asname or alias.name)
    return out


def _pre_accepts(func: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    for default in [*func.args.defaults, *func.args.kw_defaults]:
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and isinstance(default.args[0], ast.Name)
            and default.args[0].id == "get_ws_user"
        ):
            return True
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "authenticate"
        for n in ast.walk(func)
    )


def _is_websocket_route(func: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "websocket"
        for d in func.decorator_list
    )


def find_double_accepts(root: Path = SRC) -> list[str]:
    central_accepts = _central_manager_accepts()
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        accepting = _instances(tree, _accepting_connect_classes(tree))
        if central_accepts:
            accepting |= _imports_central_manager(tree)
        rel = path.relative_to(root.parent).as_posix()
        for func in ast.walk(tree):
            if not isinstance(func, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if not (_is_websocket_route(func) and _pre_accepts(func)):
                continue
            for line in _unguarded_accepts(func):
                problems.append(f"{rel}::{func.name} regel {line}: tweede accept()")
            for call in ast.walk(func):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "connect"
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id in accepting
                ):
                    problems.append(
                        f"{rel}::{func.name} regel {call.lineno}: "
                        f"{call.func.value.id}.connect() accepteert opnieuw"
                    )
    return problems


def test_no_websocket_route_accepts_twice() -> None:
    problems = find_double_accepts()
    assert not problems, (
        "Socket wordt twee keer geaccepteerd (al door get_ws_user/authenticate). "
        "Zet de accept onder `if websocket.client_state == WebSocketState.CONNECTING`:\n"
        + "\n".join(problems)
    )


def test_the_guard_sees_a_double_accept(tmp_path: Path) -> None:
    """Zelftest: een synthetisch endpoint met get_ws_user + kale accept wordt betrapt."""
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "bad.py").write_text(
        "@router.websocket('/x')\n"
        "async def ep(websocket, user=Depends(get_ws_user)):\n"
        "    await websocket.accept()\n",
        encoding="utf-8",
    )
    (pkg / "good.py").write_text(
        "@router.websocket('/y')\n"
        "async def ep(websocket):\n"
        "    await websocket.accept()\n"
        "    user = await auth.authenticate_connected_user(websocket)\n",
        encoding="utf-8",
    )
    core = pkg / "core" / "websocket"
    core.mkdir(parents=True)
    (core / "manager.py").write_text("", encoding="utf-8")
    found = find_double_accepts(pkg)
    assert [p.split("::")[0] for p in found] == ["src/bad.py"]
