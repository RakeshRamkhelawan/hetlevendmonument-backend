"""Verifies that ILearningExperienceReader and LearningExperienceData
are importable from src.core.shared.learning_interfaces and are infra-safe.

SP-DSM-COMPLETE Dag 4: eerste twee tests zijn ROOD totdat learning_interfaces.py aangemaakt is.
"""

import ast
from pathlib import Path


def test_learning_experience_reader_importable() -> None:
    """ILearningExperienceReader moet importeerbaar zijn vanuit shared."""
    from src.core.shared.learning_interfaces import ILearningExperienceReader

    assert ILearningExperienceReader is not None


def test_learning_experience_data_importable() -> None:
    """LearningExperienceData moet importeerbaar zijn vanuit shared."""
    from src.core.shared.learning_interfaces import LearningExperienceData

    assert LearningExperienceData is not None


def test_learning_interfaces_has_no_agent_runtime_imports() -> None:
    """learning_interfaces.py mag geen src.core.learning imports bevatten (infra-veilig)."""
    path = Path("src/core/shared/learning_interfaces.py")
    assert path.exists(), "src/core/shared/learning_interfaces.py bestaat nog niet (Dag 4 backlog)"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    agent_imports = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("src.core.learning")
    ]
    assert agent_imports == [], f"Verboden learning imports: {agent_imports}"
