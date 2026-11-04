"""Test dat database/models.py geen wrong-direction imports bevat (infra-only shim).

SP-DSM-COMPLETE Dag 3: agent_runtime en domain_pack imports zijn verwijderd.
"""

import ast
from pathlib import Path


def _get_import_modules() -> list[str]:
    """Lees alle ImportFrom modules uit database/models/__init__.py via AST."""
    path = Path("src/core/database/models/__init__.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_database_models_has_no_agent_runtime_imports() -> None:
    """models.py mag niet importeren van src.core.agents (agent_runtime)."""
    modules = _get_import_modules()
    agent_imports = [m for m in modules if m.startswith("src.core.agents")]
    assert agent_imports == [], f"Forbidden agent_runtime imports: {agent_imports}"


def test_database_models_has_no_learning_imports() -> None:
    """models.py mag niet importeren van src.core.learning (agent_runtime)."""
    modules = _get_import_modules()
    learning_imports = [m for m in modules if m.startswith("src.core.learning")]
    assert learning_imports == [], f"Forbidden learning imports: {learning_imports}"


def test_database_models_has_no_conversations_imports() -> None:
    """models.py mag niet importeren van src.core.conversations (domain_pack)."""
    modules = _get_import_modules()
    conv_imports = [m for m in modules if m.startswith("src.core.conversations")]
    assert conv_imports == [], f"Forbidden conversations imports: {conv_imports}"


def test_database_models_has_no_feature_flags_imports() -> None:
    """models.py mag niet importeren van src.core.feature_flags (domain_pack)."""
    modules = _get_import_modules()
    ff_imports = [m for m in modules if m.startswith("src.core.feature_flags")]
    assert ff_imports == [], f"Forbidden feature_flags imports: {ff_imports}"


def test_database_models_has_no_governance_imports() -> None:
    """models.py mag niet importeren van src.core.governance (governance)."""
    modules = _get_import_modules()
    gov_imports = [m for m in modules if m.startswith("src.core.governance")]
    assert gov_imports == [], f"Forbidden governance imports: {gov_imports}"


def test_database_models_exports_infra_only() -> None:
    """models package exporteert Base en Experiment* (infra-only)."""
    from src.core.database import models

    assert hasattr(models, "Base")
    assert hasattr(models, "Experiment")
    assert hasattr(models, "ExperimentVariant")
    assert hasattr(models, "ExperimentAssignment")
