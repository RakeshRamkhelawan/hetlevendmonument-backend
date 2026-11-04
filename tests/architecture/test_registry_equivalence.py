"""
Behavioural equivalence tests voor domain registries (ADR-033).

GESCHIEDENIS: dit bestand vergeleek de Laag 2 registries tegen 12
"_register_*"-functies die voor de ADR-033-migratie in router_registry.py
stonden. Op 2026-09-08 bleek `_read_function_source()` stil "" teruggaf zodra
zo'n functie verwijderd was (`_extract_include_router_modules("")` -> `[]` ->
`missing` altijd leeg -> triviale pass) -- een klassiek voorbeeld van het
patroon dat de rookmeldersaudit bestrijdt. Bij het repareren (hard falen i.p.v.
stil "" teruggeven) bleek de migratie voor ALLE 12 al voltooid:
router_registry.py is teruggebracht tot een "thin Laag 3 orchestrator" van
~80 regels (zie zijn eigen moduledocstring) zonder ENKELE van de 12
oorspronkelijke _register_*-functies meer, op een testonly backward-compat
shim (`_register_governance_v1`, expliciet gelabeld "Kept for tests that
import this function directly" -- en met geen andere aanroeper dan dit
bestand). De vergelijkingsbasis van alle 12 tests bestaat dus niet meer.

Onafhankelijk geverifieerd dat dit geen regressie is, niet alleen een
verdwenen referentie: `test_startup.py::test_register_all_routers_returns_
positive_count` en `test_the_api_surface_is_a_measurement.py` (hoofdmap-venv)
draaien groen -- de app boot en registreert alle routes correct via de NIEUWE
registries. De 12 tests zijn daarom verwijderd (zelfde precedent als OP-15,
quality-gates.md: "de '20 tests die we zouden verliezen' dekten een model met
nul aanroepers; verwijderen was het antwoord"), niet stil laten falen of
overslaan. `_register_governance_v1` is als gevolg daarvan ook verwijderd uit
router_registry.py (zijn enige aanroeper was deze testreeks).

De resterende test hieronder (`test_subagents_registry_in_agents_registry`)
en alle "*_flat_file_migrated_to_v1"/"*_split_into_sub_routers"-tests verderop
in dit bestand zijn NIET geraakt -- die toetsen rechtstreeks tegen de nieuwe
bestanden/routes, niet tegen verwijderde legacy-functies.
"""

import re
from pathlib import Path


def test_subagents_registry_in_agents_registry() -> None:
    """
    registries/agents.py moet een lazy import bevatten van
    src.core.api.v1.subagents (SP-API-007 Dag 3).

    NOTE: _extract_include_router_modules filters on 'router'/'endpoints' keyword;
    src.core.api.v1.subagents contains neither, so we inspect raw source text.
    """
    registry = Path("src/core/api/registries/agents.py")
    source = registry.read_text(encoding="utf-8")
    required = "src.core.api.v1.subagents"
    assert required in source, (
        f"agents.py mist een import van {required!r} (subagents domein nog niet gemigreerd)"
    )


# suppress unused import warning — re used in future extension
_ = re.compile


# =============================================================================
# SP-API-007 Dag 4 -- models_endpoints gemigreerd naar v1/models/
# =============================================================================


def test_models_flat_file_migrated_to_v1() -> None:
    """
    models_endpoints.py is gemigreerd naar src/core/api/v1/models/ (SP-API-007 Dag 4).

    Controleert dat:
    1. src/core/api/v1/models/ bestaat met alle verwachte bestanden
    2. De sub-routers samen exact de verwachte routes bevatten
    """
    models_dir = Path("src/core/api/v1/models")
    assert models_dir.exists(), "src/core/api/v1/models/ ontbreekt"
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/{model_name}/versions"),
        ("POST", "/promote"),
        ("POST", "/{model_name}/rollback"),
        ("GET", "/{model_name}/compare"),
        ("GET", "/{model_name}/production"),
        ("GET", "/{model_name}/history"),
        ("POST", "/{model_name}/archive-old"),
        ("GET", "/rules"),
    }
    sub_files = [f for f in Path("src/core/api/v1/models").glob("*_router.py")]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


# =============================================================================
# SP-API-002 Dag 3 — Sub-router split equivalence tests
# =============================================================================


def _extract_routes_from_file(file_path: Path) -> set[tuple[str, str]]:
    """Extract (METHOD, path) tuples from a router source file via regex."""
    source = file_path.read_text(encoding="utf-8")
    routes: set[tuple[str, str]] = set()
    pattern = re.compile(
        r"@(?:router|sub_router|[a-z_]+_router)\.(get|post|put|delete|patch|websocket)"
        r"\(\s*[\"']([^\"']*)[\"']"  # [^"']* — ook lege paden matchen (bijv. GET "")
    )
    for m in pattern.finditer(source):
        routes.add((m.group(1).upper(), m.group(2)))
    return routes


def _extract_routes_from_files(file_paths: list[Path]) -> set[tuple[str, str]]:
    """Extract routes from multiple files and merge."""
    result: set[tuple[str, str]] = set()
    for fp in file_paths:
        result |= _extract_routes_from_file(fp)
    return result


def test_compliance_router_split_into_sub_routers() -> None:
    """
    compliance/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 3).

    Controleert dat:
    1. Alle sub-router bestanden bestaan
    2. De sub-routers samen exact de verwachte routes bevatten (niet vacuüm-waar)
    """
    compliance_dir = Path("src/core/api/v1/compliance")
    expected_files = [
        "score_router.py",
        "gdpr_summary_router.py",
        "gdpr_dsar_router.py",
        "ai_act_summary_router.py",
        "ai_act_decisions_router.py",
        "integrity_verify_router.py",
        "integrity_status_router.py",
        "pdf_router.py",
    ]
    missing = [f for f in expected_files if not (compliance_dir / f).exists()]
    assert not missing, "De volgende compliance sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/compliance/{f}" for f in missing
    )

    # Expliciete verwachte routes (ADR-031 URL-freeze) — niet vergeleken met composite
    # omdat composite alleen include_router() bevat en geen eigen routes declareert.
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/score"),
        ("GET", "/score/history"),
        ("GET", "/report/gdpr/summary"),
        ("GET", "/report/gdpr/dsar"),
        ("GET", "/report/ai-act/summary"),
        ("GET", "/report/ai-act/decisions"),
        ("GET", "/integrity/verify"),
        ("GET", "/integrity/status"),
        ("POST", "/integrity/verify-entry"),
        ("GET", "/report/pdf"),
    }
    sub_files = [compliance_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Compliance sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_synthesis_flat_file_migrated_to_v1() -> None:
    """SP-API-006 Dag 5: synthesis_endpoints.py gemigreerd naar v1/synthesis/."""
    synth_dir = Path("src/core/api/v1/synthesis")
    assert synth_dir.exists(), "src/core/api/v1/synthesis/ ontbreekt"
    expected_files = ["synthesis_router.py"]
    missing = [f for f in expected_files if not (synth_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/synthesis"),
    }
    sub_files = [synth_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_focus_builder_router_split_into_sub_routers() -> None:
    """
    focus_builder/router.py moet zijn gesplitst in 5 Laag-1 sub-router bestanden.
    Voor de split: sub-router bestanden bestaan nog niet -> RED.
    Na de split: bestanden bestaan en dekken dezelfde routes als het origineel.
    """
    fb_dir = Path("src/core/api/v1/focus_builder")
    expected_files = [
        "flows_router.py",
        "execution_router.py",
        "pieces_router.py",
        "ai_router.py",
        "ws_status_router.py",
        "ws_chat_router.py",
    ]
    missing = [f for f in expected_files if not (fb_dir / f).exists()]
    assert not missing, "De volgende focus_builder sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/focus_builder/{f}" for f in missing
    )

    # Expliciete verwachte routes — composite bevat alleen include_router(), geen eigen routes.
    # agents_router routes zijn opzettelijk buiten scope (apart bestand, agents.py).
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/flows"),
        ("GET", "/flows"),
        ("GET", "/flows/{flow_id}"),
        ("PUT", "/flows/{flow_id}"),
        ("DELETE", "/flows/{flow_id}"),
        ("POST", "/flows/{flow_id}/execute"),
        ("GET", "/flows/{flow_id}/runs/latest"),
        ("GET", "/runs/{run_id}"),
        ("GET", "/pieces"),
        ("GET", "/pieces/{piece_name}/schema"),
        ("POST", "/pieces/sync"),
        ("POST", "/ai/suggest"),
        ("POST", "/ai/generate"),
        ("WEBSOCKET", "/flows/{flow_id}/status"),
        ("WEBSOCKET", "/ws/chat"),
    }
    sub_files = [fb_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Focus_builder sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_users_router_split_into_sub_routers() -> None:
    """
    users/router.py moet zijn gesplitst in 2 Laag-1 sub-router bestanden.
    Voor de split: sub-router bestanden bestaan nog niet -> RED.
    Na de split: bestanden bestaan en dekken dezelfde routes als het origineel.
    """
    users_dir = Path("src/core/api/v1/users")
    expected_files = [
        "me_router.py",
        "users_list_router.py",
        "users_detail_router.py",
    ]
    missing = [f for f in expected_files if not (users_dir / f).exists()]
    assert not missing, "De volgende users sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/users/{f}" for f in missing
    )

    # Expliciete verwachte routes — composite bevat alleen include_router(), geen eigen routes.
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/me"),
        ("PUT", "/me"),
        ("PUT", "/{user_id}/password"),
        ("POST", "/"),
        ("GET", "/"),
        ("GET", "/{user_id}"),
        ("PUT", "/{user_id}"),
        ("DELETE", "/{user_id}"),
    }
    sub_files = [users_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Users sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


# =============================================================================
# SP-API-002 Dag 4 -- Sub-router split equivalence tests
# =============================================================================


def test_documents_router_split_into_sub_routers() -> None:
    """
    documents/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 4).

    Controleert dat:
    1. Alle sub-router bestanden bestaan
    2. De sub-routers samen exact de verwachte routes bevatten (niet vacuem-waar)
    """
    docs_dir = Path("src/core/api/v1/documents")
    expected_files = [
        "upload_router.py",
        "crud_router.py",
        "search_router.py",
        "processing_router.py",
    ]
    missing = [f for f in expected_files if not (docs_dir / f).exists()]
    assert not missing, "De volgende documents sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/documents/{f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/upload"),
        ("GET", "/"),
        ("GET", "/search"),
        ("GET", "/{doc_id}"),
        ("PUT", "/{doc_id}"),
        ("DELETE", "/{doc_id}"),
        ("POST", "/{doc_id}/process"),
        ("GET", "/{doc_id}/status"),
        ("GET", "/{doc_id}/versions"),
    }
    sub_files = [docs_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Documents sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_orchestration_router_split_into_sub_routers() -> None:
    """
    orchestration/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 4).

    Controleert dat:
    1. Alle sub-router bestanden bestaan
    2. De sub-routers samen exact de verwachte routes bevatten (niet vacuem-waar)
    """
    orch_dir = Path("src/core/api/v1/orchestration")
    expected_files = [
        "workflow_router.py",
        "health_router.py",
        "critic_router.py",
        "stats_router.py",
    ]
    missing = [f for f in expected_files if not (orch_dir / f).exists()]
    assert not missing, "De volgende orchestration sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/orchestration/{f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/task"),
        ("GET", "/task/{workflow_id}"),
        ("POST", "/route"),
        ("GET", "/health"),
        ("GET", "/health/agent/{agent_id}"),
        ("POST", "/health/record"),
        ("POST", "/critique"),
        ("GET", "/stats"),
    }
    sub_files = [orch_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Orchestration sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_privacy_router_split_into_sub_routers() -> None:
    """
    privacy/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 4).

    Controleert dat:
    1. Alle sub-router bestanden bestaan
    2. De sub-routers samen exact de verwachte routes bevatten (niet vacuem-waar)
    """
    privacy_dir = Path("src/core/api/v1/privacy")
    expected_files = [
        "dsar_router.py",
        "consent_router.py",
        "ai_transparency_router.py",
        "human_review_router.py",
    ]
    missing = [f for f in expected_files if not (privacy_dir / f).exists()]
    assert not missing, "De volgende privacy sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/privacy/{f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("GET", "/export"),
        ("POST", "/forget"),
        ("GET", "/consent-status"),
        ("POST", "/consent"),
        ("GET", "/ai-decisions"),
        ("GET", "/profiling-opt-out"),
        ("POST", "/profiling-opt-out"),
        ("POST", "/human-review"),
        ("GET", "/human-review-requests"),
    }
    sub_files = [privacy_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Privacy sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_tools_router_split_into_sub_routers() -> None:
    """
    tools/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 4).

    Controleert dat:
    1. Alle sub-router bestanden bestaan
    2. De sub-routers samen exact de verwachte routes bevatten (niet vacuem-waar)
    """
    tools_dir = Path("src/core/api/v1/tools")
    expected_files = [
        "crud_router.py",
        "execution_router.py",
        "versions_router.py",
    ]
    missing = [f for f in expected_files if not (tools_dir / f).exists()]
    assert not missing, "De volgende tools sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/tools/{f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("GET", "/"),
        ("GET", "/{tool_id:int}"),
        ("PUT", "/{tool_id:int}"),
        ("DELETE", "/{tool_id:int}"),
        ("POST", "/{tool_id}/execute"),
        ("POST", "/{tool_id}/clone"),
        ("GET", "/{tool_id}/versions"),
        ("POST", "/{tool_id}/test"),
    }
    sub_files = [tools_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Tools sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_canvas_router_split_into_sub_routers() -> None:
    """
    canvas/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 4).

    Controleert dat:
    1. Alle sub-router bestanden bestaan
    2. De sub-routers samen exact de verwachte routes bevatten (niet vacuem-waar)
    """
    canvas_dir = Path("src/core/api/v1/canvas")
    expected_files = [
        "canvas_crud_router.py",
        "blocks_router.py",
        "connections_router.py",
        "collaborators_router.py",
        "canvas_templates_router.py",
        "canvas_ws_router.py",
    ]
    missing = [f for f in expected_files if not (canvas_dir / f).exists()]
    assert not missing, "De volgende canvas sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/canvas/{f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("GET", "/"),
        ("GET", "/{canvas_id}"),
        ("PATCH", "/{canvas_id}"),
        ("DELETE", "/{canvas_id}"),
        ("POST", "/{canvas_id}/blocks"),
        ("PATCH", "/{canvas_id}/blocks/{block_id}"),
        ("DELETE", "/{canvas_id}/blocks/{block_id}"),
        ("POST", "/{canvas_id}/connections"),
        ("DELETE", "/{canvas_id}/connections/{connection_id}"),
        ("POST", "/{canvas_id}/collaborators"),
        ("DELETE", "/{canvas_id}/collaborators/{user_id}"),
        ("GET", "/templates/list"),
        ("POST", "/from-template/{template_id}"),
        ("WEBSOCKET", "/ws/{canvas_id}"),
    }
    sub_files = [canvas_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Canvas sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_tenants_router_split_into_sub_routers() -> None:
    """tenants/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 5)."""
    tenants_dir = Path("src/core/api/v1/tenants")
    expected_files = [
        "tenants_list_router.py",
        "tenants_detail_router.py",
        "tenants_stats_router.py",
    ]
    missing = [f for f in expected_files if not (tenants_dir / f).exists()]
    assert not missing, "De volgende tenants sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/tenants/{f}" for f in missing
    )
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("GET", "/"),
        ("GET", "/{tenant_id}"),
        ("PUT", "/{tenant_id}"),
        ("DELETE", "/{tenant_id}"),
        ("GET", "/{tenant_id}/stats"),
    }
    sub_files = [tenants_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Tenants sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_als_router_split_into_sub_routers() -> None:
    """als/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 5)."""
    als_dir = Path("src/core/api/v1/als")
    expected_files = [
        "als_tasks_router.py",
        "als_health_router.py",
        "als_agents_router.py",
    ]
    missing = [f for f in expected_files if not (als_dir / f).exists()]
    assert not missing, "De volgende als sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/als/{f}" for f in missing
    )
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/tasks"),
        ("GET", "/health"),
        ("POST", "/broadcast"),
        ("GET", "/agents"),
        ("POST", "/agents/{agent_id}/ping"),
        ("GET", "/agents/{agent_id}/heartbeat"),
    }
    sub_files = [als_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "ALS sub-routers missen de volgende verwachte routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


def test_agentic_router_split_into_sub_routers() -> None:
    """agentic/router.py is gesplitst in Laag-1 sub-router bestanden (SP-API-002 Dag 5)."""
    agentic_dir = Path("src/core/api/v1/agentic")
    expected_files = [
        "agentic_routing_router.py",
        "agentic_domain_router.py",
        "agentic_roi_router.py",
    ]
    missing = [f for f in expected_files if not (agentic_dir / f).exists()]
    assert not missing, "De volgende agentic sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/agentic/{f}" for f in missing
    )
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/route"),
        ("POST", "/finance/decompose"),
        ("POST", "/packs/execute"),
        ("POST", "/feedback"),
        ("GET", "/roi/supervisor/{supervisor}"),
        ("GET", "/roi/dashboard"),
        ("GET", "/health"),
    }
    sub_files = [agentic_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Agentic sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


# =============================================================================
# SP-API-003 Dag 1 -- Workflow flat files gemigreerd naar v1/workflow/
# =============================================================================


def test_workflow_flat_files_migrated_to_v1() -> None:
    """
    Workflow flat bestanden zijn gemigreerd naar v1/workflow/ sub-routers (SP-API-003 Dag 1).

    Controleert dat:
    1. Alle sub-router bestanden bestaan in src/core/api/v1/workflow/
    2. De sub-routers samen de verwachte routes bevatten (niet vacuem-waar)
    """
    workflow_dir = Path("src/core/api/v1/workflow")
    expected_files = [
        "workflow_crud_router.py",
        "workflow_execution_router.py",
        "workflow_suggestions_router.py",
        "workflow_builder_router.py",
        "workflow_versioning_router.py",
        "workflow_generation_router.py",
        "workflow_execution_ap_router.py",
        "workflow_refinement_router.py",
        "workflow_feedback_router.py",
        "workflow_visualization_router.py",
        "router.py",
        "__init__.py",
    ]
    missing = [f for f in expected_files if not (workflow_dir / f).exists()]
    assert not missing, (
        "De volgende workflow sub-router bestanden ontbreken in src/core/api/v1/workflow/:\n"
        + "\n".join(f"  - {f}" for f in missing)
    )

    # Verwachte routes uit de nieuwe CRUD + execution routers
    # (de overige sub-routers delegeren naar de flat bestanden)
    expected_routes: set[tuple[str, str]] = {
        # workflow_crud_router.py
        ("POST", "/"),
        ("GET", "/"),
        ("GET", "/stats"),
        ("GET", "/{workflow_id}"),
        ("PUT", "/{workflow_id}"),
        ("DELETE", "/{workflow_id}"),
        # workflow_execution_router.py
        ("POST", "/{workflow_id}/execute"),
        ("GET", "/executions/{execution_id}"),
        ("GET", "/executions"),
        ("POST", "/executions/{execution_id}/cancel"),
        ("POST", "/{execution_id}/cancel"),
        ("GET", "/{execution_id}/cancel-status"),
    }
    sub_files = [
        workflow_dir / "workflow_crud_router.py",
        workflow_dir / "workflow_execution_router.py",
    ]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Workflow sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


# =============================================================================
# SP-API-003 Dag 2 -- workflow_execution_router.py split
# =============================================================================


def test_agents_flat_file_migrated_to_v1() -> None:
    """
    agent_endpoints.py is gemigreerd naar src/core/api/v1/agents/ (SP-API-003 Dag 3).

    Controleert dat:
    1. src/core/api/v1/agents/ map bestaat met alle sub-router bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    agents_dir = Path("src/core/api/v1/agents")
    assert agents_dir.exists(), "src/core/api/v1/agents/ ontbreekt"

    expected_files = [
        "agent_crud_router.py",
        "agent_execution_router.py",
        "agent_management_router.py",
        "router.py",
        "__init__.py",
        "dependencies.py",
    ]
    missing = [f for f in expected_files if not (agents_dir / f).exists()]
    assert not missing, (
        "De volgende agents sub-router bestanden ontbreken in src/core/api/v1/agents/:\n"
        + "\n".join(f"  - {f}" for f in missing)
    )

    expected_routes: set[tuple[str, str]] = {
        # agent_crud_router.py
        ("POST", "/register"),
        ("POST", "/"),
        ("POST", "/agent/register"),
        ("GET", "/"),
        ("GET", "/{agent_id}"),
        ("PATCH", "/{agent_id}"),
        # agent_execution_router.py
        ("POST", "/execute"),
        ("POST", "/agent/execute/{agent_id}"),
        ("POST", "/execute/{agent_id}"),
        # agent_management_router.py
        ("POST", "/collaborate"),
        ("GET", "/stats"),
        ("GET", "/health"),
        ("GET", "/catalog"),
    }
    sub_files = [
        agents_dir / f
        for f in ["agent_crud_router.py", "agent_execution_router.py", "agent_management_router.py"]
    ]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Agents sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


# =============================================================================
# SP-API-003 Dag 4 -- analytics_endpoints + monitoring_endpoints gemigreerd
# =============================================================================


def test_analytics_flat_file_migrated_to_v1() -> None:
    """
    analytics_endpoints.py is gemigreerd naar v1/analytics_ingest/ (SP-API-003 Dag 4).

    Controleert dat:
    1. src/core/api/v1/analytics_ingest/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    ingest_dir = Path("src/core/api/v1/analytics_ingest")
    assert ingest_dir.exists(), "src/core/api/v1/analytics_ingest/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
        "events_router.py",
        "gdpr_router.py",
        "dashboard_router.py",
        "schemas.py",
        "dependencies.py",
    ]
    missing = [f for f in expected_files if not (ingest_dir / f).exists()]
    assert not missing, "De volgende analytics_ingest bestanden ontbreken:\n" + "\n".join(
        f"  - {f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/events"),
        ("GET", "/metrics"),
        ("GET", "/sessions/{session_id}"),
        ("GET", "/health"),
        ("POST", "/events/export"),
        ("DELETE", "/events/user"),
        ("GET", "/dashboard"),
    }
    sub_files = [
        ingest_dir / f for f in ["events_router.py", "gdpr_router.py", "dashboard_router.py"]
    ]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Analytics_ingest sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_monitoring_flat_files_migrated_to_v1() -> None:
    """
    monitoring_endpoints.py + monitoring_dashboard_endpoints.py zijn gemigreerd
    naar v1/monitoring_v1/ (SP-API-003 Dag 4).

    Controleert dat:
    1. src/core/api/v1/monitoring_v1/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    mon_dir = Path("src/core/api/v1/monitoring_v1")
    assert mon_dir.exists(), "src/core/api/v1/monitoring_v1/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
        "health_router.py",
        "metrics_router.py",
        "alerts_router.py",
        "dashboard_router.py",
        "dependencies.py",
    ]
    missing = [f for f in expected_files if not (mon_dir / f).exists()]
    assert not missing, "De volgende monitoring_v1 bestanden ontbreken:\n" + "\n".join(
        f"  - {f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        # health_router
        ("GET", "/live"),
        ("GET", "/ready"),
        ("GET", "/health"),
        # metrics_router
        ("GET", "/metrics"),
        ("GET", "/metrics/prometheus"),
        ("GET", "/performance"),
        ("GET", "/logs/analysis"),
        # alerts_router
        ("GET", "/alerts"),
        ("POST", "/trigger_alert"),
        ("GET", "/alert/{alert_id}"),
        ("POST", "/profiler/start"),
        ("POST", "/profiler/stop"),
        ("GET", "/profiler/functions"),
        ("DELETE", "/profiler/clear"),
        ("GET", "/system/status"),
        ("GET", "/mock-usage"),
        ("GET", "/mock-usage/{component}"),
        ("POST", "/mock-usage/start-monitoring"),
        ("POST", "/mock-usage/stop-monitoring"),
        ("GET", "/mock-usage/thresholds"),
        # dashboard_router
        ("GET", "/dashboard/health"),
        ("GET", "/system-overview"),
        ("GET", "/system-health"),
        ("GET", "/agents"),
        ("GET", "/performance"),
        ("GET", "/learning"),
        ("GET", "/alerts"),
        ("GET", "/dashboard"),
        ("WEBSOCKET", "/ws/dashboard"),
        ("WEBSOCKET", "/ws/alerts"),
        ("GET", "/get_dashboard"),
        ("GET", "/get_widget/{widget_id}"),
        ("GET", "/overview"),
        ("GET", "/metrics"),
        ("GET", "/api/metrics"),
    }
    sub_files = [
        mon_dir / f
        for f in [
            "health_router.py",
            "metrics_router.py",
            "alerts_router.py",
            "dashboard_router.py",
        ]
    ]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Monitoring_v1 sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_workflow_execution_split_into_sub_routers() -> None:
    """
    workflow_execution_router.py (449r) is gesplitst in 2 sub-router bestanden
    (SP-API-003 Dag 2).

    Controleert dat:
    1. workflow_execution_core_router.py + workflow_execution_cancel_router.py bestaan
    2. Samen dekken ze alle 6 routes van het origineel
    """
    workflow_dir = Path("src/core/api/v1/workflow")
    expected_files = [
        "workflow_execution_core_router.py",
        "workflow_execution_cancel_router.py",
    ]
    missing = [f for f in expected_files if not (workflow_dir / f).exists()]
    assert not missing, (
        "De volgende workflow execution sub-router bestanden ontbreken:\n"
        + "\n".join(f"  - src/core/api/v1/workflow/{f}" for f in missing)
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/{workflow_id}/execute"),
        ("GET", "/executions/{execution_id}"),
        ("GET", "/executions"),
        ("POST", "/executions/{execution_id}/cancel"),
        ("POST", "/{execution_id}/cancel"),
        ("GET", "/{execution_id}/cancel-status"),
    }
    sub_files = [workflow_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Workflow execution sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


# =============================================================================
# SP-API-003 Dag 5 -- audit + knowledge + memory gemigreerd naar v1/
# =============================================================================


def test_audit_flat_file_migrated_to_v1() -> None:
    """
    audit_endpoints.py is gemigreerd naar src/core/api/v1/audit/ (SP-API-003 Dag 5).

    Controleert dat:
    1. src/core/api/v1/audit/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    audit_dir = Path("src/core/api/v1/audit")
    assert audit_dir.exists(), "src/core/api/v1/audit/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
        "missions_router.py",
        "schemas.py",
        "dependencies.py",
    ]
    missing = [f for f in expected_files if not (audit_dir / f).exists()]
    assert not missing, "De volgende audit bestanden ontbreken:\n" + "\n".join(
        f"  - {f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("GET", "/missions"),
        ("GET", "/missions/{mission_id}/export"),
    }
    sub_files = [audit_dir / "missions_router.py"]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Audit sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_memory_flat_file_migrated_to_v1() -> None:
    """
    memory_endpoints.py is gemigreerd naar src/core/api/v1/memory/ (SP-API-003 Dag 5).

    Controleert dat:
    1. src/core/api/v1/memory/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    memory_dir = Path("src/core/api/v1/memory")
    assert memory_dir.exists(), "src/core/api/v1/memory/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
        "config_router.py",
        "index_router.py",
        "schemas.py",
        "dependencies.py",
    ]
    missing = [f for f in expected_files if not (memory_dir / f).exists()]
    assert not missing, "De volgende memory bestanden ontbreken:\n" + "\n".join(
        f"  - {f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("GET", "/config"),
        ("PUT", "/config"),
        ("GET", "/index"),
        ("POST", "/index"),
        ("DELETE", "/index"),
    }
    sub_files = [memory_dir / "config_router.py", memory_dir / "index_router.py"]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Memory sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


def test_security_flat_file_migrated_to_v1() -> None:
    """security_endpoints.py is gemigreerd naar v1/security/ (SP-API-004 Dag 1)."""
    security_dir = Path("src/core/api/v1/security")
    assert security_dir.exists(), "src/core/api/v1/security/ ontbreekt"

    expected_files = [
        "auth_router.py",
        "report_router.py",
        "management_router.py",
        "monitoring_router.py",
        "alerts_router.py",
    ]
    missing = [f for f in expected_files if not (security_dir / f).exists()]
    assert not missing, "Ontbrekende sub-router bestanden:\n" + "\n".join(missing)

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/auth/login"),
        ("GET", "/report"),
        ("GET", "/events"),
        ("GET", "/rate-limits"),
        ("POST", "/block-ip"),
        ("POST", "/unblock-ip"),
        ("GET", "/health"),
        ("POST", "/cleanup"),
        ("GET", "/audit-logs"),
        ("GET", "/alerts"),
        ("POST", "/alerts/{alert_id}/acknowledge"),
        ("POST", "/alerts/{alert_id}/resolve"),
        ("GET", "/summary"),
        ("GET", "/verify-integrity"),
    }
    sub_files = [security_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "Security sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


def test_missions_flat_file_migrated_to_v1() -> None:
    """mission_endpoints.py is gemigreerd naar v1/missions/ (SP-API-004 Dag 2)."""
    missions_dir = Path("src/core/api/v1/missions")
    assert missions_dir.exists(), "src/core/api/v1/missions/ ontbreekt"
    expected_files = ["crud_router.py", "lifecycle_router.py"]
    missing = [f for f in expected_files if not (missions_dir / f).exists()]
    assert not missing, "Ontbrekende sub-router bestanden:\n" + "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("POST", "/simple"),
        ("GET", "/"),
        ("GET", "/{mission_id}"),
        ("DELETE", "/{mission_id}"),
        ("POST", "/{mission_id}/approve"),
        ("POST", "/{mission_id}/reject"),
        ("GET", "/{mission_id}/steps/{step_id}/explainability"),
    }
    sub_files = [missions_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "Missions sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


def test_cva_flat_file_migrated_to_v1() -> None:
    """cva_endpoints.py is gemigreerd naar v1/cva/ (SP-API-004 Dag 3)."""
    cva_dir = Path("src/core/api/v1/cva")
    assert cva_dir.exists()
    expected_files = [
        "chat_router.py",
        "legacy_router.py",
        "conversations_router.py",
        "management_router.py",
        "public_router.py",
    ]
    missing = [f for f in expected_files if not (cva_dir / f).exists()]
    assert not missing, "Ontbrekende sub-router bestanden:\n" + "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/chat"),
        ("POST", "/chat/stream"),
        ("POST", "/chat/legacy"),
        ("GET", "/conversations"),
        ("GET", "/conversations/{conversation_id}"),
        ("DELETE", "/conversations/{conversation_id}"),
        ("GET", "/status"),
        ("GET", "/status-detail"),
        ("POST", "/optimize"),
        ("GET", "/analytics"),
        ("GET", "/health"),
        ("POST", "/shutdown"),
        ("POST", "/create_agent"),
        ("POST", "/execute/{agent_id}"),
    }
    sub_files = [cva_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "CVA sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


# =============================================================================
# SP-API-004 Dag 4 -- health + tenant_management gemigreerd naar v1/
# =============================================================================


def test_health_flat_file_migrated_to_v1() -> None:
    """
    health_endpoints.py is gemigreerd naar src/core/api/v1/health/ (SP-API-004 Dag 4).

    Controleert dat:
    1. src/core/api/v1/health/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    health_dir = Path("src/core/api/v1/health")
    assert health_dir.exists(), "src/core/api/v1/health/ ontbreekt"
    expected_files = ["checks_router.py", "llm_router.py"]
    missing = [f for f in expected_files if not (health_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/health"),
        ("GET", "/health/ready"),
        ("GET", "/health/db"),
        ("GET", "/ready"),
        ("GET", "/health/deep"),
        ("GET", "/health/paperclip"),
        ("GET", "/llm"),
    }
    sub_files = [health_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_tenant_management_flat_file_migrated_to_v1() -> None:
    """
    tenant_management_endpoints.py is gemigreerd naar src/core/api/v1/tenant_management/
    (SP-API-004 Dag 4).

    Controleert dat:
    1. src/core/api/v1/tenant_management/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    tm_dir = Path("src/core/api/v1/tenant_management")
    assert tm_dir.exists(), "src/core/api/v1/tenant_management/ ontbreekt"
    expected_files = ["crud_router.py"]
    missing = [f for f in expected_files if not (tm_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("GET", "/"),
        ("GET", "/{tenant_id}"),
        ("PUT", "/{tenant_id}"),
        ("DELETE", "/{tenant_id}"),
    }
    sub_files = [tm_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_knowledge_flat_file_migrated_to_v1() -> None:
    """
    knowledge_endpoints.py is gemigreerd naar src/core/api/v1/knowledge/ (SP-API-003 Dag 5).

    Controleert dat:
    1. src/core/api/v1/knowledge/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    knowledge_dir = Path("src/core/api/v1/knowledge")
    assert knowledge_dir.exists(), "src/core/api/v1/knowledge/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
        "crud_router.py",
        "search_router.py",
        "admin_router.py",
        "schemas.py",
    ]
    missing = [f for f in expected_files if not (knowledge_dir / f).exists()]
    assert not missing, "De volgende knowledge bestanden ontbreken:\n" + "\n".join(
        f"  - {f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/create"),
        ("GET", "/get"),
        ("PUT", "/update"),
        ("DELETE", "/delete"),
        ("GET", "/"),
        ("POST", "/search"),
        ("GET", "/categories"),
        ("POST", "/index/rebuild"),
    }
    sub_files = [
        knowledge_dir / f for f in ["crud_router.py", "search_router.py", "admin_router.py"]
    ]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, (
        "Knowledge sub-routers missen de volgende verwachte routes:\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
    )


# =============================================================================
# SP-API-004 Dag 5 -- autonomous_endpoints gemigreerd naar v1/autonomous/
# =============================================================================


def test_autonomous_flat_file_migrated_to_v1() -> None:
    """autonomous_endpoints.py is gemigreerd naar v1/autonomous/ (SP-API-004 Dag 5)."""
    auto_dir = Path("src/core/api/v1/autonomous")
    assert auto_dir.exists()
    expected_files = [
        "agents_router.py",
        "healing_router.py",
        "code_router.py",
        "emergence_router.py",
    ]
    missing = [f for f in expected_files if not (auto_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/agents/create"),
        ("GET", "/agents/templates"),
        ("POST", "/agents/templates"),
        ("GET", "/agents/factory/metrics"),
        ("POST", "/healing/report-failure"),
        ("GET", "/healing/status"),
        ("POST", "/healing/execute-repair/{failure_id}"),
        ("POST", "/code/generate"),
        ("GET", "/code/templates"),
        ("GET", "/code/metrics"),
        ("POST", "/emergence/facilitate"),
        ("GET", "/emergence/behaviors"),
        ("GET", "/emergence/intelligence-levels"),
        ("GET", "/status"),
        ("GET", "/health"),
    }
    sub_files = [auto_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_gdpr_compliance_flat_file_migrated_to_v1() -> None:
    """gdpr_compliance_endpoints.py is gemigreerd naar v1/gdpr_compliance/ (SP-API-005 Dag 1)."""
    gdpr_dir = Path("src/core/api/v1/gdpr_compliance")
    assert gdpr_dir.exists(), "src/core/api/v1/gdpr_compliance/ ontbreekt"

    expected_files = [
        "access_router.py",
        "erasure_router.py",
        "portability_router.py",
        "utility_router.py",
    ]
    missing = [f for f in expected_files if not (gdpr_dir / f).exists()]
    assert not missing, "Ontbrekende sub-router bestanden:\n" + "\n".join(missing)

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/export"),
        ("GET", "/export/download/{export_id}"),
        ("POST", "/delete-all"),
        ("GET", "/audit-trail"),
        ("GET", "/status"),
        ("GET", "/checklist"),
        ("PUT", "/checklist/{requirement_id}"),
    }
    sub_files = [gdpr_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "GDPR sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


# =============================================================================
# SP-API-005 Dag 2 -- admin + user_management gemigreerd naar v1/
# =============================================================================


def test_admin_flat_file_migrated_to_v1() -> None:
    """admin_endpoints.py is gemigreerd naar v1/admin/ (SP-API-005 Dag 2)."""
    admin_dir = Path("src/core/api/v1/admin")
    assert admin_dir.exists()
    expected_files = ["users_router.py", "monitoring_router.py"]
    missing = [f for f in expected_files if not (admin_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/create_user"),
        ("POST", "/assign_role/{user_id}"),
        ("GET", "/dashboard"),
        ("GET", "/users"),
        ("GET", "/system"),
        ("GET", "/logs"),
        ("GET", "/monitor"),
        ("GET", "/public"),
    }
    sub_files = [admin_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_user_management_flat_file_migrated_to_v1() -> None:
    """user_management_endpoints.py is gemigreerd naar v1/user_management/ (SP-API-005 Dag 2)."""
    um_dir = Path("src/core/api/v1/user_management")
    assert um_dir.exists()
    expected_files = ["crud_router.py", "profile_router.py"]
    missing = [f for f in expected_files if not (um_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("GET", "/"),
        ("PUT", "/me"),
        ("GET", "/{user_id}"),
        ("PUT", "/{user_id}"),
        ("DELETE", "/{user_id}"),
        ("PATCH", "/{user_id}/status"),
        ("POST", "/{user_id}/roles"),
    }
    sub_files = [um_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


# =============================================================================
# SP-API-005 Dag 3 -- activepieces_endpoints gemigreerd naar v1/activepieces/
# =============================================================================


def test_tool_broker_flat_file_migrated_to_v1() -> None:
    """tool_broker_endpoints.py is gemigreerd naar v1/tool_broker/ (SP-API-005 Dag 4)."""
    tb_dir = Path("src/core/api/v1/tool_broker")
    assert tb_dir.exists(), "src/core/api/v1/tool_broker/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
        "crud_router.py",
        "execution_router.py",
        "management_router.py",
        "dependencies.py",
    ]
    missing = [f for f in expected_files if not (tb_dir / f).exists()]
    assert not missing, "Ontbrekende tool_broker bestanden:\n" + "\n".join(missing)

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/"),
        ("GET", "/"),
        ("POST", "/execute"),
        ("GET", "/list"),
        ("GET", "/{tool_name}/status"),
        ("GET", "/history"),
        ("POST", "/{tool_name}/enable"),
        ("POST", "/{tool_name}/disable"),
        ("GET", "/history/recent"),
    }
    sub_files = [
        tb_dir / f for f in ["crud_router.py", "execution_router.py", "management_router.py"]
    ]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "Tool_broker sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


def test_governance_admin_flat_file_migrated_to_v1() -> None:
    """governance_endpoints.py is gemigreerd naar v1/governance_admin/ (SP-API-005 Dag 4)."""
    gov_dir = Path("src/core/api/v1/governance_admin")
    assert gov_dir.exists(), "src/core/api/v1/governance_admin/ ontbreekt"

    expected_files = [
        "__init__.py",
        "router.py",
    ]
    missing = [f for f in expected_files if not (gov_dir / f).exists()]
    assert not missing, "Ontbrekende governance_admin bestanden:\n" + "\n".join(missing)

    expected_routes: set[tuple[str, str]] = {
        ("GET", "/anomalies"),
        ("GET", "/risks/{mission_id}"),
    }
    sub_files = [gov_dir / "router.py", gov_dir / "router_anomalies.py", gov_dir / "router_risk.py"]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "Governance_admin sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


def test_activepieces_flat_file_migrated_to_v1() -> None:
    """activepieces_endpoints.py is gemigreerd naar v1/activepieces/ (SP-API-005 Dag 3)."""
    ap_dir = Path("src/core/api/v1/activepieces")
    assert ap_dir.exists()
    expected_files = [
        "catalog_router.py",
        "flows_router.py",
        "execution_router.py",
        "connections_router.py",
        "health_router.py",
    ]
    missing = [f for f in expected_files if not (ap_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/source-badges"),
        ("GET", "/pieces/{piece_name}"),
        ("GET", "/flows"),
        ("GET", "/flows/{flow_id}"),
        ("POST", "/flows"),
        ("PUT", "/flows/{flow_id}"),
        ("DELETE", "/flows/{flow_id}"),
        ("POST", "/flows/{flow_id}/toggle"),
        ("POST", "/flows/validate"),
        ("POST", "/flows/{flow_id}/execute"),
        ("GET", "/flows/{flow_id}/runs"),
        ("GET", "/flows/{flow_id}/runs/{run_id}"),
        ("POST", "/flows/{flow_id}/runs/{run_id}/retry"),
        ("POST", "/flows/{flow_id}/runs/{run_id}/cancel"),
        ("GET", "/connections"),
        ("GET", "/connections/{connection_id}"),
        ("POST", "/connections"),
        ("DELETE", "/connections/{connection_id}"),
        ("POST", "/connections/{connection_id}/test"),
        ("PUT", "/connections/{connection_id}"),
        ("GET", "/connections/oauth/{app_name}/url"),
        ("POST", "/connections/oauth/callback"),
        ("GET", "/health"),
        ("GET", "/health/detailed"),
    }
    sub_files = [ap_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


# =============================================================================
# SP-API-005 Dag 5 -- rbac_endpoints + management_endpoints gemigreerd naar v1/
# =============================================================================


def test_rbac_flat_file_migrated_to_v1() -> None:
    """rbac_endpoints.py is gemigreerd naar v1/rbac/ (SP-API-005 Dag 5)."""
    rbac_dir = Path("src/core/api/v1/rbac")
    assert rbac_dir.exists()
    expected_files = ["permissions_router.py", "roles_router.py", "assignment_router.py"]
    missing = [f for f in expected_files if not (rbac_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/users/{user_id}/permissions"),
        ("POST", "/users/assign-role"),
        ("POST", "/users/revoke-role"),
        ("POST", "/roles/create"),
        ("POST", "/permissions/check"),
        ("GET", "/roles"),
        ("GET", "/roles/{role_id}/permissions"),
        ("POST", "/roles/{role_id}/permissions"),
        ("DELETE", "/roles/{role_id}/permissions"),
        ("GET", "/roles/{role_id}/users"),
        ("POST", "/users/assign-role/bulk"),
        ("POST", "/users/revoke-role/bulk"),
    }
    sub_files = [rbac_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


# =============================================================================
# SP-API-006 Dag 1 -- copilot_endpoints gemigreerd naar v1/copilot_intent/
# =============================================================================


def test_copilot_intent_flat_file_migrated_to_v1() -> None:
    """
    copilot_endpoints.py is gemigreerd naar src/core/api/v1/copilot_intent/ (SP-API-006 Dag 1).

    Controleert dat:
    1. src/core/api/v1/copilot_intent/ bestaat met parse_router.py
    2. De sub-router bevat de verwachte POST /parse route
    """
    ci_dir = Path("src/core/api/v1/copilot_intent")
    assert ci_dir.exists(), "src/core/api/v1/copilot_intent/ ontbreekt"
    expected_files = ["parse_router.py"]
    missing = [f for f in expected_files if not (ci_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/parse"),
    }
    sub_files = [ci_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_cva_flat_files_consolidated_to_v1() -> None:
    """cva_chat/cva_admin/cva_conversations zijn geconsolideerd in v1/cva/ (SP-API-006 Dag 2)."""
    cva_dir = Path("src/core/api/v1/cva")
    assert cva_dir.exists()
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/chat"),
        ("POST", "/chat/legacy"),
        ("POST", "/chat/stream"),
        ("GET", "/health"),
        ("GET", "/status"),
        ("GET", "/status-detail"),
        ("GET", "/analytics"),
        ("POST", "/optimize"),
        ("POST", "/shutdown"),
        ("GET", "/conversations"),
        ("GET", "/conversations/{conversation_id}"),
        ("DELETE", "/conversations/{conversation_id}"),
        ("DELETE", "/conversations/{conversation_id}/messages"),
    }
    sub_files = [f for f in cva_dir.glob("*_router.py")]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "v1/cva/ mist routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )


def test_feature_flags_flat_file_migrated_to_v1() -> None:
    """
    feature_flags_endpoints.py is gemigreerd naar src/core/api/v1/feature_flags/ (SP-API-006 Dag 3).

    Controleert dat:
    1. src/core/api/v1/feature_flags/ bestaat met alle verwachte sub-router bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    ff_dir = Path("src/core/api/v1/feature_flags")
    assert ff_dir.exists(), "src/core/api/v1/feature_flags/ ontbreekt"
    expected_files = ["features_router.py", "tenant_router.py", "admin_router.py"]
    missing = [f for f in expected_files if not (ff_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/features"),
        ("GET", "/tenant/features"),
        ("GET", "/tenant/tier"),
        ("POST", "/admin/features/{feature}/toggle"),
        ("GET", "/tenant/features/{feature}/check"),
    }
    sub_files = [ff_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_sentiment_scanner_flat_file_migrated_to_v1() -> None:
    """sentiment_scanner_endpoints.py is gemigreerd naar v1/sentiment_scanner/ (SP-API-006 Dag 4)."""
    ss_dir = Path("src/core/api/v1/sentiment_scanner")
    assert ss_dir.exists()
    expected_files = ["scanner_router.py"]
    missing = [f for f in expected_files if not (ss_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/status"),
        ("POST", "/analyze"),
        ("POST", "/batch-analyze"),
        ("POST", "/generate-report"),
        ("GET", "/demo"),
    }
    sub_files = [ss_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_production_flat_file_migrated_to_v1() -> None:
    """production_endpoints.py is gemigreerd naar v1/production/ (SP-API-006 Dag 4)."""
    prod_dir = Path("src/core/api/v1/production")
    assert prod_dir.exists()
    expected_files = ["health_router.py", "operations_router.py", "reporting_router.py"]
    missing = [f for f in expected_files if not (prod_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/health"),
        ("POST", "/initialize"),
        ("POST", "/test/comprehensive"),
        ("GET", "/health-assessment"),
        ("GET", "/deployment-status"),
        ("GET", "/system-integration-status"),
        ("POST", "/restart-system"),
        ("GET", "/production-report"),
        ("GET", "/performance-baseline"),
    }
    sub_files = [prod_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_experimentation_flat_file_migrated_to_v1() -> None:
    """
    experimentation_endpoints.py is gemigreerd naar src/core/api/v1/experimentation/
    (SP-API-007 Dag 1).

    Controleert dat:
    1. src/core/api/v1/experimentation/ bestaat met alle verwachte bestanden
    2. De sub-routers samen de verwachte routes bevatten
    """
    exp_dir = Path("src/core/api/v1/experimentation")
    assert exp_dir.exists(), "src/core/api/v1/experimentation/ ontbreekt"
    expected_files = ["experiments_router.py"]
    missing = [f for f in expected_files if not (exp_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/create"),
        ("GET", "/{experiment_id}"),
        ("POST", "/{experiment_id}/start"),
        ("POST", "/{experiment_id}/pause"),
        ("POST", "/{experiment_id}/stop"),
        ("POST", "/{experiment_id}/assign"),
        ("GET", "/{experiment_id}/metrics"),
        ("POST", "/{experiment_id}/results"),
        ("GET", "/active"),
    }
    sub_files = [exp_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_ai_features_flat_file_migrated_to_v1() -> None:
    """
    ai_features_endpoints.py is gemigreerd naar src/core/api/v1/ai_features/
    (SP-API-007 Dag 2).

    Controleert dat:
    1. src/core/api/v1/ai_features/ bestaat met alle verwachte sub-router bestanden
    2. De sub-routers samen exact de verwachte routes bevatten
    """
    ai_dir = Path("src/core/api/v1/ai_features")
    assert ai_dir.exists(), "src/core/api/v1/ai_features/ ontbreekt"

    expected_files = [
        "learning_router.py",
        "routing_router.py",
        "analytics_router.py",
        "system_router.py",
    ]
    missing = [f for f in expected_files if not (ai_dir / f).exists()]
    assert not missing, "De volgende ai_features sub-router bestanden ontbreken:\n" + "\n".join(
        f"  - src/core/api/v1/ai_features/{f}" for f in missing
    )

    expected_routes: set[tuple[str, str]] = {
        ("POST", "/learning/event"),
        ("GET", "/learning/insights"),
        ("POST", "/routing/route"),
        ("POST", "/analytics/predict"),
        ("GET", "/system/status"),
        ("GET", "/capabilities"),
    }
    sub_files = [f for f in Path("src/core/api/v1/ai_features").glob("*_router.py")]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_management_flat_file_migrated_to_v1() -> None:
    """management_endpoints.py is gemigreerd naar v1/management/ (SP-API-005 Dag 5)."""
    mgmt_dir = Path("src/core/api/v1/management")
    assert mgmt_dir.exists()
    expected_files = ["agents_router.py", "tasks_router.py", "logs_router.py"]
    missing = [f for f in expected_files if not (mgmt_dir / f).exists()]
    assert not missing, "\n".join(missing)
    expected_routes: set[tuple[str, str]] = {
        ("GET", "/agents"),
        ("POST", "/agents/{agent_id}/pause"),
        ("POST", "/agents/{agent_id}/resume"),
        ("POST", "/agents/{agent_id}/restart"),
        ("GET", "/costs"),
        ("GET", "/tasks"),
        ("POST", "/tasks/{task_id}/prioritize"),
        ("POST", "/tasks/{task_id}/cancel"),
        ("GET", "/logs"),
        ("GET", "/logs/broadcast-queue"),
    }
    sub_files = [mgmt_dir / f for f in expected_files]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))


def test_management_has_no_approval_respond_route() -> None:
    """OP-264 (2026-10-04): `POST /approvals/{approval_id}/respond` bestaat NIET meer.

    `test_management_flat_file_migrated_to_v1` EISTE deze route (hij stond in `expected_routes`);
    die eis is omgedraaid. Goedkeuren gaat alleen via `hitl_tickets`
    (`/api/v1/tools/hitl/approve|reject`), niet via een lijst in procesgeheugen. Beide
    routerbestanden worden gecontroleerd: de v1-subrouter EN het legacy platte bestand.
    """
    mgmt_dir = Path("src/core/api/v1/management")
    files = [mgmt_dir / "tasks_router.py", Path("src/core/api/management_endpoints.py")]
    actual_routes = _extract_routes_from_files(files)

    assert ("POST", "/approvals/{approval_id}/respond") not in actual_routes


def test_prediction_flat_file_migrated_to_v1() -> None:
    """prediction_endpoints.py is gemigreerd naar v1/prediction/ (SP-API-007 Dag 5)."""
    pred_dir = Path("src/core/api/v1/prediction")
    assert pred_dir.exists(), "src/core/api/v1/prediction/ ontbreekt"
    expected_routes: set[tuple[str, str]] = {
        ("POST", "/initialize"),
        ("GET", "/status"),
        ("POST", "/collect-metrics"),
        ("POST", "/predict"),
        ("GET", "/predictions/recent"),
        ("GET", "/metrics/history"),
        ("POST", "/optimize/execute"),
        ("GET", "/analytics/trends"),
        ("GET", "/health"),
    }
    sub_files = [f for f in pred_dir.glob("*_router.py")]
    actual_routes = _extract_routes_from_files(sub_files)
    missing_routes = expected_routes - actual_routes
    assert not missing_routes, "Prediction sub-routers missen routes:\n" + "\n".join(
        f"  - {m} {p}" for m, p in sorted(missing_routes)
    )
