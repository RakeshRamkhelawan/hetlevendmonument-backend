"""Architecture test: src.core.types is 'shared' in DSM MODULE_MAP, niet 'agent_runtime'."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DSM_SCRIPT_PATH = REPO_ROOT / "scripts/dsm_full_analysis.py"


def _extract_module_map(script_src: str) -> dict[str, str]:
    tree = ast.parse(script_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MODULE_MAP":
                    if isinstance(node.value, ast.Dict):
                        result = {}
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                result[k.value] = v.value
                        return result
    return {}


def test_src_core_types_classified_as_shared():
    """src.core.types MOET als 'shared' geclassificeerd zijn in MODULE_MAP -- SP-DSM-001.

    types.py is een platformbrede shared types hub (AgentType, TaskStatus, IsolationLevel,
    ThreatLevel re-export). Classificatie als 'agent_runtime' creert een onterechte KRITIEK
    circulaire afhankelijkheid met src.core.shared (interfaces.py + config.py importeren hieruit).
    """
    src = DSM_SCRIPT_PATH.read_text(encoding="utf-8")
    module_map = _extract_module_map(src)
    classification = module_map.get("src.core.types")
    assert classification == "shared", (
        f"src.core.types is geclassificeerd als '{classification}', verwacht 'shared'. "
        "Pas MODULE_MAP aan in scripts/dsm_full_analysis.py: "
        "'src.core.types': 'agent_runtime' -> 'shared'. "
        "Zie SP-DSM-001."
    )
