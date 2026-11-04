"""Architecture tests voor SP-DSM-007 bevestigde schendingen.

Alle tests hieronder zijn ROOD bij aanmaak en worden GROEN na de fixes.
De messaging-circular (test_messaging_services_circular) blijft ROOD
totdat SP-DSM-008 dit adresseert.
"""

import ast
from pathlib import Path

SRC = Path("src/core")


def _get_imports(filepath: Path) -> list[str]:
    """Retourneert alle import-strings (module-namen) uit een Python-bestand.

    Telt GEEN imports in TYPE_CHECKING-blokken mee.
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    type_checking_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                for child in ast.walk(node):
                    type_checking_nodes.add(id(child))

    imports = []
    for node in ast.walk(tree):
        if id(node) in type_checking_nodes:
            continue
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
    return imports


# ---------------------------------------------------------------------------
# Taak 3: infra -> core_api
# ---------------------------------------------------------------------------


def test_container_does_not_import_core_api():
    """TODO(SP-DSM-009): container.py (agent_runtime) mag NOOIT src.core.api importeren.

    container.py is gereclassificeerd als 'agent_runtime' (SP-DSM-009, was 'infra').
    src.core.api is geclassificeerd als 'core_api' (I=0.99, instabiel).
    agent_runtime -> core_api is een SDP-schending EN een circulaire dep.

    Gevonden schendingen (SP-DSM-007, inmiddels opgelost):
      container.py:422  from src.core.api.ai_features_endpoints import _build_learning_engine
      container.py:435  from src.core.api.ai_features_endpoints import _build_intelligent_router
      container.py:442  from src.core.api.ai_features_endpoints import _build_predictive_analytics
    """
    container = SRC / "container.py"
    assert container.exists(), "src/core/container.py niet gevonden"
    for imp in _get_imports(container):
        assert not imp.startswith("src.core.api"), (
            f"container.py importeert src.core.api: {imp!r}\n"
            "Fix: vervang door directe import uit src.core.ai.* (de API-stub is een doorgeefluik)."
        )


# ---------------------------------------------------------------------------
# Taak 4: domain_pack -> core_api
# ---------------------------------------------------------------------------


def test_evaluation_service_does_not_import_api_schemas():
    """TODO(SP-DSM-007): batch_evaluation_service.py mag GEEN api-schemas importeren.

    src.core.evaluation is geclassificeerd als 'domain_pack' (I=0.38).
    Response-schemas horen niet in de api-laag maar in de domain-laag zelf.

    Gevonden schending:
      batch_evaluation_service.py:14  from src.core.api.schemas.evaluation_schemas import (...)

    Fix: verplaats de schemas naar src.core.evaluation.schemas en laat
    api/schemas/evaluation_schemas.py re-exporteren.
    """
    svc = SRC / "evaluation" / "batch_evaluation_service.py"
    assert svc.exists(), "src/core/evaluation/batch_evaluation_service.py niet gevonden"
    for imp in _get_imports(svc):
        assert not imp.startswith("src.core.api"), (
            f"batch_evaluation_service.py importeert src.core.api: {imp!r}\n"
            "Fix: verplaats EvaluationBatchRunResponse e.a. naar src.core.evaluation.schemas."
        )


# ---------------------------------------------------------------------------
# Taak 5a: agent_runtime -> core_api (factory.py)
# ---------------------------------------------------------------------------


def test_copilot_factory_does_not_import_prana_api():
    """TODO(SP-DSM-007): copilot/council/factory.py mag GEEN api-cache importeren.

    factory.py is onderdeel van 'agent_runtime' (I=0.78).
    get_contract_manager hoort niet in de api-laag te leven.

    Gevonden schending:
      factory.py:184  from src.core.api.v1._prana_contracts_cache import get_contract_manager

    Fix: verplaats get_contract_manager naar src.core.copilot.prana_budget_cache
    en laat api/v1/_prana_contracts_cache.py re-exporteren.
    """
    factory = SRC / "copilot" / "council" / "factory.py"
    assert factory.exists(), "src/core/copilot/council/factory.py niet gevonden"
    for imp in _get_imports(factory):
        assert not imp.startswith("src.core.api"), (
            f"copilot/council/factory.py importeert src.core.api: {imp!r}\n"
            "Fix: gebruik src.core.copilot.prana_budget_cache i.p.v. api/v1/_prana_contracts_cache."
        )


# ---------------------------------------------------------------------------
# Taak 5b: agent_runtime -> core_api (dependencies.py)
# ---------------------------------------------------------------------------


def test_copilot_dependencies_does_not_import_app_state_from_api():
    """TODO(SP-DSM-007): copilot/dependencies.py mag GEEN app_state uit api importeren.

    dependencies.py is onderdeel van 'agent_runtime' (I=0.78).
    app_state is een globale dict die niet in de api-laag hoort te leven.

    Gevonden schending:
      dependencies.py:100  from src.core.api.setup.app_state import app_state

    Fix: verplaats app_state naar src.core.shared.app_state en laat
    api/setup/app_state.py re-exporteren voor backward compat.
    """
    deps = SRC / "copilot" / "dependencies.py"
    assert deps.exists(), "src/core/copilot/dependencies.py niet gevonden"
    for imp in _get_imports(deps):
        assert not imp.startswith("src.core.api"), (
            f"copilot/dependencies.py importeert src.core.api: {imp!r}\n"
            "Fix: gebruik src.core.shared.app_state i.p.v. api/setup/app_state."
        )


# ---------------------------------------------------------------------------
# Backlog (SP-DSM-008): messaging <-> cva_tasks circulaire dep
# ---------------------------------------------------------------------------


def test_messaging_services_do_not_import_tasks():
    """TODO(SP-DSM-008): messaging-services mogen NIET src.core.tasks importeren.

    src.core.services.messaging -> 'agent_runtime' (I=0.78)
    src.core.tasks -> 'worker' (I=0.90, instabiel)

    Stabiele laag mag niet afhangen van instabielere laag (SDP-schending).
    Bovendien: cva_tasks.py importeert TERUG naar messaging.gateway -> bidirectioneel.

    Gevonden schendingen:
      telegram.py:6   from src.core.tasks.cva_tasks import process_cva_message
      whatsapp.py:7   from src.core.tasks.cva_tasks import process_cva_message

    Fix (DSM-008): gebruik event-bus of maak een thin adapter in services-laag
    die de Dramatiq-actor wraptvia een interface zodat de tasks-import verdwijnt.

    BEWUST ROOD: dit backlog-item wordt gefixed in SP-DSM-008.
    """
    messaging_dir = SRC / "services" / "messaging"
    violations = []
    for pyfile in messaging_dir.rglob("*.py"):
        if "__pycache__" in str(pyfile):
            continue
        for imp in _get_imports(pyfile):
            if imp.startswith("src.core.tasks") or imp.startswith("src.workers"):
                violations.append(f"{pyfile.name}: {imp}")
    assert not violations, (
        f"messaging-services importeren tasks/worker ({len(violations)} schendingen):\n"
        + "\n".join(violations)
        + "\nBacklog: SP-DSM-008 (bidirectioneel circulair met cva_tasks.gateway import)."
    )
