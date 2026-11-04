"""ARCH-005: CVAService MOET LearningMixin implementeren of een gedocumenteerde vrijstelling hebben.

Rode backlog-marker -- BLIJFT ROOD totdat SP-CVA-HIGH-002 gefixed is.
TODO(SP-CVA-HIGH-002): Documenteer vrijstelling of implementeer LearningMixin in CVAService.
"""

import ast
from pathlib import Path


def test_cva_service_learning_mixin_decision_documented():
    """CVAService heeft geen LearningMixin -- architectuurbeslissing vereist (ADR-022).

    TODO(SP-CVA-HIGH-002): Documenteer vrijstelling of implementeer LearningMixin.
    """
    src = (Path(__file__).resolve().parents[2] / "src/core/services/cva_service.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    cva_class = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "CVAService"),
        None,
    )
    assert cva_class is not None, "CVAService klasse niet gevonden in cva_service.py"

    base_names: list[str] = []
    for base in cva_class.bases:
        if isinstance(base, ast.Name):
            base_names.append(base.id)
        elif isinstance(base, ast.Attribute):
            base_names.append(f"{base.attr}")

    has_learning = any("LearningMixin" in name for name in base_names)
    has_exemption = "# ADR-022 exempt:" in src

    assert has_learning or has_exemption, (
        "CVAService heeft geen LearningMixin (ADR-022) en geen gedocumenteerde vrijstelling. "
        "Fix in SP-CVA-HIGH-002: voeg LearningMixin toe of voeg comment toe: "
        "# ADR-022 exempt: <reden> zodat deze test groen wordt."
    )
