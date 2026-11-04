"""TDD tests -- LawfulBasisRegistry wiring in API lifecycle (SP-DLP-002 Dag 2, GDPR-001).

These are *structural* (source-text) tests: they verify that the routers call
validate_endpoint_access().  They fail RED before wiring and go GREEN after.
"""

from pathlib import Path


def test_consent_router_calls_lawful_basis_validation() -> None:
    """consent_router.py moet LawfulBasisRegistry aanroepen (GDPR Art. 6)."""
    src = Path("src/core/api/v1/privacy/consent_router.py").read_text(encoding="utf-8")
    assert "LawfulBasisRegistry" in src or "validate_endpoint_access" in src, (
        "consent_router.py bevat geen LawfulBasisRegistry aanroep -- "
        "GDPR Art. 6 rechtmatige grondslag niet gehandhaafd"
    )


def test_portability_router_calls_lawful_basis_validation() -> None:
    """portability_router.py moet LawfulBasisRegistry aanroepen (GDPR Art. 6/20)."""
    src = Path("src/core/api/v1/gdpr_compliance/portability_router.py").read_text(encoding="utf-8")
    assert "LawfulBasisRegistry" in src or "validate_endpoint_access" in src, (
        "portability_router.py bevat geen LawfulBasisRegistry aanroep -- "
        "GDPR Art. 20 portability zonder Art. 6 grondslag"
    )


def test_access_router_calls_lawful_basis_validation() -> None:
    """access_router.py moet LawfulBasisRegistry aanroepen (GDPR Art. 6/15)."""
    src = Path("src/core/api/v1/gdpr_compliance/access_router.py").read_text(encoding="utf-8")
    assert "LawfulBasisRegistry" in src or "validate_endpoint_access" in src, (
        "access_router.py bevat geen LawfulBasisRegistry aanroep -- "
        "GDPR Art. 15 access-recht zonder Art. 6 grondslag"
    )


def test_governance_dependencies_module_exists() -> None:
    """src/core/governance/dependencies.py moet bestaan na wiring."""
    dep_file = Path("src/core/governance/dependencies.py")
    assert dep_file.exists(), (
        "src/core/governance/dependencies.py bestaat niet -- "
        "LawfulBasisRegistry Depends-factory ontbreekt"
    )
