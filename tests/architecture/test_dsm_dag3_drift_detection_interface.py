"""Architecture test: drift_detection.py moet LearningExperience via interface injecteren.

TODO(SP-DSM-DAG4): drift_detection.py importeert src.core.learning.models.LearningExperience
direct als ORM-klasse. Dit is tijdelijk gereclassificeerd als agent_runtime in MODULE_MAP
(SP-DSM-COMPLETE Dag 3 pragmatische stap). De definitieve fix is een ILearningExperienceReader
protocol in src.core.shared.interfaces met injectie in DriftDetector.__init__.

Deze test BLIJFT ROOD totdat de definitieve fix geimplementeerd is (SP-DSM-DAG4).
"""

import ast
from pathlib import Path


def test_drift_detection_has_no_direct_learning_import() -> None:
    """DriftDetector mag NIET direct LearningExperience importeren -- gebruik interface.

    TODO(SP-DSM-DAG4): Implementeer ILearningExperienceReader en injecteer via __init__.
    """
    path = Path("src/core/monitoring/drift_detection.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    direct_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("src.core.learning"):
                direct_imports.append(node.module)
    assert direct_imports == [], (
        "drift_detection.py importeert direct van src.core.learning. "
        "Implementeer ILearningExperienceReader protocol en injecteer via __init__. "
        "Backlog: SP-DSM-DAG4."
    )
