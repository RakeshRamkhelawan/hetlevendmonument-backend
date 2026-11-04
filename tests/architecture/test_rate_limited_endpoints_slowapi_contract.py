"""Architecture test: rate-limited endpoints must satisfy slowapi's call contract.

Background (OP-11, 2026-07-31):
- get_limiter() builds every Limiter with headers_enabled=True
  (src/core/middleware/rate_limiter.py:135) -- in ALL environments, production
  included.
- With headers_enabled, slowapi's wrapper (site-packages/slowapi/extension.py,
  async_wrapper) does two things on every single request:

      request = kwargs.get("request", args[idx] if args else None)
      if not isinstance(request, Request):
          raise Exception("parameter `request` must be an instance of ...Request")
      ...
      response = await func(*args, **kwargs)
      if not isinstance(response, Response):
          self._inject_headers(kwargs.get("response"), ...)   # needs a param NAMED response
      else:
          self._inject_headers(response, ...)                 # return value is used

  So an endpoint decorated with @limiter.limit raises an unhandled Exception ->
  HTTP 500 on EVERY request unless both hold:
    1. it has a parameter named `request` that is annotated as a starlette
       Request (a Pydantic body model that happens to be named `request` fails
       the isinstance check), and
    2. it either has a parameter named `response` (slowapi looks it up by name
       via kwargs.get("response")) or it returns a real Response instance.

- This bit us for real: 10 live endpoints returned 500 on every call, hidden
  behind 13 red integration tests that nobody ran (integration baseline drifted
  from 0 failures on 2026-06-22 to 34 on 2026-07-31). Two of them --
  scheduling connect_provider/trigger_sync -- had no test coverage at all and
  were only found by this scan.

IMPORTANT subtlety this test encodes: a Pydantic model named `*Response`
(e.g. HealthReportResponse) is NOT a starlette Response. Matching the return
annotation by substring silently passes broken endpoints, so the comparison
below is exact.
"""

import ast
from functools import lru_cache
from pathlib import Path

SRC_ROOT = Path("src")

# starlette/fastapi Response classes: returning one of these satisfies slowapi
# without needing a `response` parameter.
RESPONSE_RETURN_TYPES = {
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "FileResponse",
    "ORJSONResponse",
    "UJSONResponse",
}

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _is_limiter_limit(decorator: ast.expr) -> bool:
    """Match @limiter.limit(...), @auth_limiter.limit(...), @x.limiter.limit(...)."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not isinstance(func, ast.Attribute) or func.attr != "limit":
        return False
    if isinstance(func.value, ast.Name):
        return "limiter" in func.value.id.lower()
    if isinstance(func.value, ast.Attribute):
        return "limiter" in func.value.attr.lower()
    return False


def _params(node: FunctionNode) -> list[ast.arg]:
    args = node.args
    return list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)


def _has_param_named(node: FunctionNode, name: str) -> bool:
    return any(arg.arg == name for arg in _params(node))


def _returns_response_instance(node: FunctionNode) -> bool:
    """True if the return annotation is a real Response type (exact match)."""
    if node.returns is None:
        return False
    names = {part.strip() for part in ast.unparse(node.returns).replace("|", " ").split()}
    return bool(names & RESPONSE_RETURN_TYPES)


def _request_param_violation(node: FunctionNode) -> str | None:
    """Return a reason string if slowapi's isinstance(request, Request) would fail."""
    for arg in _params(node):
        if arg.arg == "websocket":
            return None
        if arg.arg == "request":
            annotation = ast.unparse(arg.annotation) if arg.annotation else "<geen annotatie>"
            # Accept Request and Annotated[Request, ...]; reject anything else
            # (a Pydantic body model named `request` passes decoration but
            # fails the runtime isinstance check).
            names = {part.strip(" [],") for part in annotation.replace("|", " ").split()}
            if "Request" in names:
                return None
            return f"`request` is geannoteerd als {annotation}, geen starlette Request"
    return "geen `request`- of `websocket`-parameter"


@lru_cache(maxsize=1)
def _rate_limited_endpoints() -> tuple[tuple[tuple[Path, FunctionNode], ...], tuple[str, ...]]:
    """(endpoints, fouten) -- een bestand dat niet leest/parseert werd voorheen stil
    overgeslagen (except: continue, geen telling), zonder enige bescherming behalve een
    totaaldrempel (>=50) op een ANDERE test dan de twee die de echte slowapi-contract
    toetsen. `@lru_cache` voorkomt dat alle drie testfuncties src/ apart herscannen."""
    found: list[tuple[Path, FunctionNode]] = []
    fouten: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                _is_limiter_limit(dec) for dec in node.decorator_list
            ):
                found.append((path, node))
    return tuple(found), tuple(fouten)


def test_no_source_file_is_silently_unreadable_or_unparseable() -> None:
    """Vangnet PER BESTAND: de totaaldrempel hieronder wordt door de gezonde bestanden
    altijd gehaald, dus een enkel overgeslagen bestand -- juist een nieuw, niet-conform
    @limiter.limit-endpoint -- kon daaronder onzichtbaar blijven."""
    _, fouten = _rate_limited_endpoints()
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd "
        "op het slowapi-contract:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_rate_limited_endpoints_can_receive_ratelimit_headers() -> None:
    """slowapi needs a `response` param, or a Response return value, to inject headers."""
    violations: list[str] = []

    endpoints, _ = _rate_limited_endpoints()
    for path, node in endpoints:
        if _has_param_named(node, "response"):
            continue
        if _returns_response_instance(node):
            continue
        violations.append(
            f"{path.as_posix()}:{node.lineno} {node.name}: geen `response`-parameter en "
            "retourneert geen Response -- slowapi's _inject_headers krijgt None en "
            "gooit een Exception (HTTP 500 op ELKE request)"
        )

    assert not violations, (
        "Elk @limiter.limit-endpoint MOET slowapi header-injectie kunnen ontvangen "
        "(OP-11 preventie-regel):\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_rate_limited_endpoints_expose_a_real_request_object() -> None:
    """slowapi asserts isinstance(request, starlette Request) before checking limits."""
    violations: list[str] = []

    endpoints, _ = _rate_limited_endpoints()
    for path, node in endpoints:
        reason = _request_param_violation(node)
        if reason:
            violations.append(f"{path.as_posix()}:{node.lineno} {node.name}: {reason}")

    assert not violations, (
        "Elk @limiter.limit-endpoint MOET een echte starlette Request-parameter hebben "
        "(OP-11 preventie-regel):\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_scan_actually_finds_the_rate_limited_endpoints() -> None:
    """Guard against a silently empty scan (a vacuous pass is worse than a failure)."""
    endpoints, _ = _rate_limited_endpoints()
    assert len(endpoints) >= 50, (
        f"Verwacht minimaal 50 @limiter.limit-endpoints in src/, gevonden {len(endpoints)} -- "
        "de scan matcht het decorator-patroon niet meer (regel _is_limiter_limit)"
    )
