"""
Architecture test: domain_pack mag GEEN circulaire afhankelijkheid hebben met integrations.

SP-DSM-016 Dag 3 -- AUDIT-DSM-006
Root cause: focus_builder/service.py importeert activepieces direct (domain_pack->integrations);
hybrid_search.py importeert evaluation_service (integrations->domain_pack).
Fix: focus_builder reclassificatie naar integrations + knowledge_manager naar domain_pack.
"""

import subprocess
import sys
from pathlib import Path


def _run_dsm() -> str:
    result = subprocess.run(
        [sys.executable, "scripts/dsm_full_analysis.py"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    return result.stdout + result.stderr


def test_dsm016_no_domain_integrations_circular_pair():
    """domain_pack <-> integrations circulair MOET gesloten zijn.

    TODO(SP-DSM-016-dag3): Faalt totdat focus_builder/knowledge gereclassificeerd zijn.
    Bewijs (na fix): DSM toont dit paar niet meer in CIRCULAIRE DEPENDENCIES.
    """
    output = _run_dsm()
    assert "domain_pack <-> integrations" not in output, (
        "domain_pack <-> integrations circular pair bestaat nog. "
        "Fix: 'src.core.focus_builder': 'integrations' in MODULE_MAP + SOURCE_DIRS update."
    )


def test_dsm016_focus_builder_not_classified_as_domain_pack():
    """src.core.focus_builder mag NIET geclassificeerd zijn als domain_pack.

    TODO(SP-DSM-016-dag3): Faalt totdat MODULE_MAP bijgewerkt is.
    """
    content = Path("scripts/dsm_full_analysis.py").read_text(encoding="utf-8")
    assert '"src.core.focus_builder": "domain_pack"' not in content, (
        "MODULE_MAP classificeert focus_builder nog als 'domain_pack'. "
        "Wijzig naar 'integrations' -- focus_builder importeert activepieces direct."
    )


def test_dsm016_evaluation_not_classified_as_domain_pack():
    """src.core.evaluation mag NIET geclassificeerd zijn als domain_pack.

    FA-002 correctie: statisch bewijs dat evaluation-reclassificatie (dag 3) geldig is.
    """
    content = Path("scripts/dsm_full_analysis.py").read_text(encoding="utf-8")
    assert '"src.core.evaluation": "domain_pack"' not in content, (
        "MODULE_MAP classificeert evaluation nog als 'domain_pack'. "
        "Wijzig naar 'integrations' -- hybrid_search importeert evaluation_service direct."
    )
