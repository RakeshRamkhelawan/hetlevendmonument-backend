"""SP-API-010 Dag 2 -- architecture tests: route-migratie gaps.

5 routes in Batch-A flat files hebben GEEN v1/ equivalent.
Proxy stubs houden deze routes levend maar delegeren naar een stub-response.
Deze tests bewijzen dat de v1/ endpoints ontbreken -- ze blijven rood totdat
SP-API-011 de ontbrekende v1/ routes aanmaakt.

Routes zonder v1/ equivalent:
  tool_endpoints.py         GET  /integrations/catalog  -- geen v1/tools/catalog
  tool_endpoints.py         GET  /integrations/search   -- geen v1/tools/search
  agentic_flow_endpoints.py WS   /ws/builder            -- v1/ heeft /ws/agent/stream (ander pad)
  template_endpoints.py     POST /{id}/deploy           -- geen v1/company/template /deploy
  template_endpoints.py     GET  /search/               -- geen v1/company/template /search
"""

import ast
from pathlib import Path


def _has_route_in_dir(directory: str, path_fragment: str) -> bool:
    """Geeft True als een route-pad-fragment gevonden wordt in een v1/ directory."""
    base = Path(directory)
    if not base.exists():
        return False
    for f in base.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                if not isinstance(dec.func, ast.Attribute):
                    continue
                if not dec.args:
                    continue
                try:
                    route_path = ast.literal_eval(dec.args[0])
                    if path_fragment in str(route_path):
                        return True
                except Exception:
                    continue
    return False


def _file_has_route(filepath: str, path_fragment: str) -> bool:
    """Scan alleen het opgegeven bestand op een route-pad-fragment."""
    path = Path(filepath)
    if not path.exists():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            if not isinstance(dec.func, ast.Attribute):
                continue
            if not dec.args:
                continue
            try:
                route_path = ast.literal_eval(dec.args[0])
                if path_fragment in str(route_path):
                    return True
            except Exception:
                continue
    return False


def test_v1_tools_has_catalog_route() -> None:
    """TODO(SP-API-011): tool_endpoints.py GET /integrations/catalog delegeert naar v1/tools/.

    Proxy stub in tool_endpoints.py bevat TODO(SP-API-011) marker.
    v1/ equivalent aanmaken in SP-API-011.
    """
    found = _has_route_in_dir("src/core/api/v1/tools", "/catalog")
    assert found, (
        "v1/tools/ bevat geen route met '/catalog' -- "
        "SP-API-011: maak GET /api/v1/tools/integrations/catalog aan in v1/tools/"
    )


def test_v1_tools_has_integrations_search_route() -> None:
    """TODO(SP-API-011): tool_endpoints.py GET /integrations/search delegeert naar v1/tools/.

    Proxy stub retourneert deprecation-hint. v1/ equivalent aanmaken in SP-API-011.
    """
    found = _has_route_in_dir("src/core/api/v1/tools", "/integrations/search")
    assert found, (
        "v1/tools/ bevat geen route met '/integrations/search' -- "
        "SP-API-011: maak GET /api/v1/tools/integrations/search aan in v1/tools/"
    )


def test_v1_agentic_has_ws_builder_route() -> None:
    """TODO(SP-API-011): agentic_flow_endpoints.py WS /ws/builder naar v1/ migreren.

    v1/agentic/websocket.py biedt /ws/agent/stream -- ander pad, ander contract.
    SP-API-011: voeg /ws/builder alias toe of documenteer frontend-migratiepad.
    """
    found = _has_route_in_dir("src/core/api/v1/agentic", "/ws/builder")
    assert found, (
        "v1/agentic/ bevat geen WebSocket route '/ws/builder' -- "
        "SP-API-011: voeg alias toe (huidig pad: /ws/agent/stream)"
    )


def test_v1_template_has_deploy_route() -> None:
    """TODO(SP-API-011): template_endpoints.py POST /{id}/deploy heeft geen v1/ equivalent.

    v1/company/template_router.py heeft: GET /, GET /{id}, POST /{id}/instantiate.
    SP-API-011: voeg POST /{template_id}/deploy toe aan template_router.py.
    """
    found = _file_has_route("src/core/api/v1/company/template_router.py", "/deploy")
    assert found, (
        "v1/company/template_router.py bevat geen '/deploy' route -- "
        "SP-API-011: voeg POST /{template_id}/deploy toe"
    )


def test_v1_template_has_search_route() -> None:
    """TODO(SP-API-011): template_endpoints.py GET /search/ heeft geen v1/ equivalent.

    SP-API-011: voeg GET /search/ toe aan v1/company/template_router.py.
    """
    found = _file_has_route("src/core/api/v1/company/template_router.py", "/search")
    assert found, (
        "v1/company/template_router.py bevat geen '/search' route -- "
        "SP-API-011: voeg GET /search/ toe"
    )
