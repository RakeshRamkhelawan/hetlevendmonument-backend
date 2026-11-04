"""
Architecture test: governance mag NIET importeren vanuit domain_pack.

SP-DSM-016 Dag 2 -- AUDIT-DSM-005
Root cause: src.core.ai_quality geclassificeerd als governance terwijl het
procedures-data (domain_pack) importeert -- creeert governance->domain_pack backwards edges.
Fix: ai_quality reclassificeren naar domain_pack in MODULE_MAP + SOURCE_DIRS
     (scripts/dsm_full_analysis.py).
"""

import subprocess
import sys
from pathlib import Path


def _run_dsm() -> str:
    """Run DSM scanner and return output."""
    result = subprocess.run(
        [sys.executable, "scripts/dsm_full_analysis.py"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    return result.stdout + result.stderr


def test_dsm016_governance_no_domain_pack_circular_pair():
    """domain_pack <-> governance circular pair MOET gesloten zijn.

    TODO(SP-DSM-016-dag2): Faalt totdat ai_quality gereclassificeerd is als domain_pack.
    Bewijs (na fix): DSM toont dit paar niet meer in CIRCULAIRE DEPENDENCIES.
    """
    output = _run_dsm()
    assert "domain_pack <-> governance" not in output, (
        "domain_pack <-> governance circular pair bestaat nog. "
        "Fix: verander 'src.core.ai_quality': 'governance' -> 'domain_pack' in MODULE_MAP "
        "en update SOURCE_DIRS in scripts/dsm_full_analysis.py."
    )


def test_dsm016_ai_quality_not_classified_as_governance():
    """src.core.ai_quality mag NIET geclassificeerd zijn als governance.

    TODO(SP-DSM-016-dag2): Faalt totdat MODULE_MAP bijgewerkt is.
    """
    dsm_path = Path("scripts/dsm_full_analysis.py")
    content = dsm_path.read_text(encoding="utf-8")
    assert '"src.core.ai_quality": "governance"' not in content, (
        "MODULE_MAP classificeert src.core.ai_quality nog steeds als 'governance'. "
        "Wijzig naar 'domain_pack' -- ai_quality leest procedures-data (domain_pack)."
    )
