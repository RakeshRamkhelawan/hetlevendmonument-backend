"""core_api -> agent_runtime architecture bewakers. Dag 5 SP-DSM-COMPLETE.

Baseline scan 2026-06-13: 108 import-statements in ~39 bestanden (brief schatte ~79 op basis
van steekproef; volledige scan geeft 108 -- verschil gedocumenteerd in BE-DSM-004).
93.7% Category-1 (legitieme orchestratie).
Category-2 violatie: admin_learning_endpoints.py (gdpr_models + twin_models direct importeren).

TODO(SP-DSM-DAG6): Reduceer Category-2 via service-laag facade in admin_learning_endpoints.py.
Verlaag threshold naar 100 zodra Category-2 opgelost is (108 baseline - 4 Category-2 = 104;
100 is bereikbare target met kleine marge).
"""

import ast
import pytest
from pathlib import Path


def test_core_api_agent_runtime_imports_within_baseline() -> None:
    """Bewaakt dat core_api->agent_runtime NIET boven 120 groeit (Dag 5 baseline 108).

    TODO(SP-DSM-DAG6): verlaag threshold naar 100 na Category-2 fix in admin_learning_endpoints.py.
    """
    AGENT_RUNTIME_PREFIXES = (
        "src.core.agents",
        "src.core.learning",
        "src.core.autonomy",
        "src.core.als",
        "src.core.scheduling.voice",
        "src.core.scheduling.agents",
        "src.core.monitoring.drift_detection",
        "src.core.monitoring.dashboard",
        "src.core.monitoring.agent_circuit_metrics",
        "src.core.scheduling.api.voice_routes",
        "src.core.scheduling.memory_consolidation_job",
    )
    CORE_API_DIRS = [Path("src/core/api"), Path("src/api"), Path("src/core/dependencies.py")]

    count = 0
    ontbrekend = [str(d) for d in CORE_API_DIRS if not d.exists()]
    fouten: list[str] = []
    gescand = 0
    for src_dir in CORE_API_DIRS:
        if not src_dir.exists():
            continue
        files = [src_dir] if src_dir.is_file() else list(src_dir.rglob("*.py"))
        for f in files:
            if not f.exists():
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8-sig"))
            except (OSError, SyntaxError, UnicodeDecodeError) as e:
                fouten.append(f"{f}: {e}")
                continue
            gescand += 1
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if any(node.module.startswith(p) for p in AGENT_RUNTIME_PREFIXES):
                        count += 1

    assert not ontbrekend, (
        f"Deze paden in CORE_API_DIRS bestaan niet: {ontbrekend}. Verplaatst of hernoemd? "
        "Deze guard telt dan minder dan de echte koppelingen en het plafond hieronder "
        "wordt betekenisloos."
    )
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET meegeteld:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )
    assert gescand >= 90, (
        f"Slechts {gescand} bestanden gescand over {CORE_API_DIRS} -- dat lijkt een "
        "(bijna) lege scan. Het plafond hieronder wordt dan altijd triviaal gehaald."
    )
    assert count <= 120, (
        f"core_api->agent_runtime groeide boven 120: {count} import-statements. "
        "SP-DSM-DAG6: reduceer Category-2 imports in admin_learning_endpoints.py naar 0."
    )


def test_admin_learning_endpoints_no_direct_orm_models() -> None:
    """admin_learning_endpoints.py mag GEEN directe ORM-model imports uit learning hebben.

    TODO(SP-DSM-DAG6): verplaats gdpr_models + twin_models toegang naar LearningGDPRService
    methoden zodat de router alleen de service-laag aanroept.

    Huidige violaties (2026-06-13):
      line 13: from src.core.learning.gdpr_models import (GDPRDeleteUserRequest, ...)
      line 20: from src.core.learning.twin_models import TenantLLMBudget
    """
    target = Path("src/core/api/admin_learning_endpoints.py")
    assert target.exists(), (
        "admin_learning_endpoints.py niet gevonden -- als dit bestand verwijderd of hernoemd is, "
        "verifieer dan dat de ORM-imports naar LearningGDPRService gemigreerd zijn "
        "VOOR de verwijdering. SP-DSM-DAG6."
    )

    ORM_MODEL_MODULES = (
        "src.core.learning.gdpr_models",
        "src.core.learning.twin_models",
    )

    violations: list[str] = []
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except Exception as e:
        pytest.fail(
            f"Kon {target} niet parsen: {e} -- bestand is onleesbaar of bevat syntax errors."
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for prefix in ORM_MODEL_MODULES:
                if node.module.startswith(prefix):
                    names = [a.name for a in node.names]
                    violations.append(f"  line {node.lineno}: from {node.module} import {names}")

    assert not violations, (
        "admin_learning_endpoints.py importeert ORM-modellen direct (Category-2 violatie):\n"
        + "\n".join(violations)
        + "\nSP-DSM-DAG6: ontsluiten via LearningGDPRService service-laag."
    )
