"""
Architecture test: auth <-> governance circulair MOET gesloten zijn.

SP-DSM-016 Dag 4
Root cause:
  - auth/auth_service.py:16  -> governance.services.audit_service (toplevel)
  - auth/dependencies.py:445 -> governance.services.audit_service (lazy try-except)
  - security/security_audit_service.py:32 -> governance.models.AuditLog (toplevel)
  - governance/rate_limiter.py:57 -> security.rate_limiter (lazy async, terug-kant)
Fix: governance.models->shared + security.rate_limiter->shared +
     governance.services.audit_service->shared in MODULE_MAP.
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


def test_dsm016_no_auth_governance_circular_pair():
    """auth <-> governance circulair MOET gesloten zijn.

    TODO(SP-DSM-016-dag4): Faalt totdat MODULE_MAP overrides voor governance.models,
    security.rate_limiter en governance.services.audit_service aanwezig zijn.
    Bewijs (na fix): DSM toont dit paar niet meer in CIRCULAIRE DEPENDENCIES.
    """
    output = _run_dsm()
    assert "auth <-> governance" not in output, (
        "auth <-> governance circular pair bestaat nog. "
        "Fix: governance.models->shared + security.rate_limiter->shared + "
        "governance.services.audit_service->shared in MODULE_MAP "
        "(scripts/dsm_full_analysis.py)."
    )


def test_dsm016_security_rate_limiter_classified_as_shared():
    """src.core.security.rate_limiter moet als shared geclassificeerd zijn.

    Reden: RedisRateLimiter is een infra-primitive (geen src.* imports).
    Fix B sluit de governance->auth terug-kant: governance/rate_limiter.py
    importeert security.rate_limiter (lazy); na reclassificatie is het governance->shared.
    governance.models->shared is bewust NIET gedaan (zou governance I > 0.40 veroorzaken,
    SP-DSM-011 regressie). De circulaire is gesloten door alleen de terug-kant te breken.
    """
    content = Path("scripts/dsm_full_analysis.py").read_text(encoding="utf-8")
    assert '"src.core.security.rate_limiter": "shared"' in content, (
        "MODULE_MAP mist 'src.core.security.rate_limiter': 'shared'. "
        "Voeg toe na de src.core.security: auth entry (override, longest-prefix-wins)."
    )
