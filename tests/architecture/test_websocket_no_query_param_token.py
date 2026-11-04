"""Architecture test: geen enkel WebSocket-pad mag een token uit de query string halen.

Achtergrond (SEC-AGT-004, uitgebreid tijdens OP-11 2026-07-31):
- OWASP ASVS V7 verbiedt sessie-identifiers in query strings: ze lekken in access logs,
  browsergeschiedenis, proxy logs en de Referer-header.
- SEC-AGT-004 verwijderde het ``?token=``-pad uit
  ``WebSocketAuthenticator._extract_token``, maar drie andere paden bleven het accepteren:
  ``get_current_user_ws`` (auth/dependencies.py), en de twee focus-builder websockets die
  hun eigen ``token: str | None = Query(None)`` hadden. De hardening was daarmee
  omzeilbaar -- en niets detecteerde dat, omdat er een test bestond die het oude gedrag
  juist VASTLEGDE (``test_ws_auth_query_param_backward_compat``).

Deze test dekt het structureel af in plaats van per bestand: hij scant de AST van src/ op
beide vormen waarin een WS-token uit de query kan komen.

Toegestane token-bronnen (zie WebSocketAuthenticator._extract_token):
1. HTTP-only cookie ``access_token`` (canoniek)
2. ``Sec-WebSocket-Protocol`` subprotocol
3. ``Authorization: Bearer``-header
"""

import ast
from functools import lru_cache
from pathlib import Path

SRC_ROOT = Path("src")

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# Namen die een JWT/sessietoken aanduiden. `conversation_id`, `flow_id` enzovoort mogen
# uiteraard wel in de query staan -- die zijn geen credential.
TOKEN_PARAM_NAMES = {"token", "access_token", "jwt", "auth_token"}


def _is_websocket_route(node: FunctionNode) -> bool:
    """True voor functies met een @<router>.websocket(...)-decorator."""
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute) and target.attr == "websocket":
            return True
    return False


def _query_token_params(node: FunctionNode) -> list[str]:
    """Parameters die een token via fastapi Query(...) uit de query string halen."""
    args = node.args
    all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    defaults: list[ast.expr | None] = [None] * (
        len(all_args) - len(args.defaults) - len(args.kwonlyargs)
    )
    defaults += list(args.defaults) + list(args.kw_defaults)

    offenders: list[str] = []
    for arg, default in zip(all_args, defaults, strict=False):
        if arg.arg not in TOKEN_PARAM_NAMES:
            continue
        rendered = ast.unparse(default) if default is not None else ""
        annotation = ast.unparse(arg.annotation) if arg.annotation else ""
        # Een token-parameter op een websocket-route komt per definitie uit de query
        # string: WebSockets hebben geen request body en headers/cookies worden via het
        # websocket-object gelezen, niet via een parameter.
        if "Query(" in rendered or (rendered == "" and "Depends" not in annotation):
            offenders.append(arg.arg)
    return offenders


def _reads_token_from_query_params(tree: ast.AST) -> list[int]:
    """Regelnummers van `...query_params.get("token")`-achtige expressies."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "get":
            continue
        owner = func.value
        if not (isinstance(owner, ast.Attribute) and owner.attr == "query_params"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value in TOKEN_PARAM_NAMES:
                hits.append(node.lineno)
    return hits


@lru_cache(maxsize=1)
def _parsed_src_files() -> tuple[list[tuple[Path, ast.AST]], list[str]]:
    """(pad+AST voor elk bestand in src/, parse-fouten).

    Gedeeld door de drie tests hieronder, die eerder elk onafhankelijk dezelfde
    (SyntaxError, UnicodeDecodeError) stil wegvingen. Het bestaande vangnet
    (test_scan_actually_finds_websocket_routes) deelde dezelfde except en dezelfde
    blinde vlek: een bestand met precies een query-param-tokenlek EN een syntaxfout
    viel buiten alle drie de scans zonder dat een van hen dat opmerkte.
    """
    bomen: list[tuple[Path, ast.AST]] = []
    fouten: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            bomen.append((path, ast.parse(path.read_text(encoding="utf-8-sig"))))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path.as_posix()}: {exc}")
    return bomen, fouten


def test_no_source_file_is_silently_unparseable() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag geen van de drie scans
    hieronder blind maken. Zonder deze test delen alle drie hun blinde vlek."""
    _, fouten = _parsed_src_files()
    assert not fouten, (
        "Deze bestanden onder src/ konden niet gelezen/geparsed worden en zijn NIET "
        "gecontroleerd op een WebSocket-token-lek via de query string:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )


def test_no_websocket_route_accepts_a_query_param_token() -> None:
    """Een WS-route mag geen token-parameter uit de query string aannemen."""
    violations: list[str] = []

    bomen, _fouten = _parsed_src_files()
    for path, tree in bomen:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_websocket_route(
                node
            ):
                for param in _query_token_params(node):
                    violations.append(f"{path.as_posix()}:{node.lineno} {node.name}: `{param}`")

    assert not violations, (
        "WebSocket-routes mogen geen token uit de query string accepteren "
        "(SEC-AGT-004, OWASP ASVS V7 -- tokens lekken in logs, history, proxies en de "
        "Referer-header). Gebruik de access_token-cookie, het Sec-WebSocket-Protocol "
        "subprotocol of de Authorization-header:\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_no_code_reads_a_token_from_query_params() -> None:
    """Geen enkele module mag een token uit `query_params` lezen."""
    violations: list[str] = []

    bomen, _fouten = _parsed_src_files()
    for path, tree in bomen:
        for lineno in _reads_token_from_query_params(tree):
            violations.append(f"{path.as_posix()}:{lineno}")

    assert not violations, (
        "Een token uit `query_params` lezen is verboden (SEC-AGT-004). Dit omzeilt de "
        "hardening die in WebSocketAuthenticator._extract_token al is doorgevoerd:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_scan_actually_finds_websocket_routes() -> None:
    """Vangnet tegen een vacuum-pass als het decorator-patroon verandert."""
    bomen, _fouten = _parsed_src_files()
    count = sum(
        1
        for _, tree in bomen
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_websocket_route(node)
    )

    assert count >= 10, (
        f"Verwacht minimaal 10 @router.websocket-routes in src/, gevonden {count} -- "
        "de scan matcht het decorator-patroon niet meer (_is_websocket_route)."
    )
