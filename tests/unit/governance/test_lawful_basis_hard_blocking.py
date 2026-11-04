"""TDD: LawfulBasisRegistry hard-blocking -- SP-DLP-003 Dag 1 (GDPR-001 fase 2)."""

import re
from pathlib import Path

_HARD_BLOCK_PATTERN = re.compile(
    r"except LawfulBasisMissingError.*?raise HTTPException\(\s*status_code=451",
    re.DOTALL,
)
_LOGGER_ERROR_PATTERN = re.compile(
    r"except LawfulBasisMissingError.*?logger\.error\(",
    re.DOTALL,
)


def test_consent_router_raises_451_in_lawful_basis_block():
    """consent_router.py moet HTTPException(451) gooien IN except LawfulBasisMissingError -- 2x."""
    src = Path("src/core/api/v1/privacy/consent_router.py").read_text(encoding="utf-8")
    matches = _HARD_BLOCK_PATTERN.findall(src)
    assert len(matches) >= 2, (
        f"consent_router.py heeft {len(matches)} HTTPException(451) raise(s) in "
        "LawfulBasisMissingError blokken -- verwacht 2 (get_consent_status + update_consent)"
    )
    assert len(_LOGGER_ERROR_PATTERN.findall(src)) >= 2, (
        "consent_router.py logt geen logger.error in LawfulBasisMissingError blokken"
    )


def test_portability_router_raises_451_in_lawful_basis_block():
    """portability_router.py moet HTTPException(451) gooien IN except LawfulBasisMissingError."""
    src = Path("src/core/api/v1/gdpr_compliance/portability_router.py").read_text(encoding="utf-8")
    matches = _HARD_BLOCK_PATTERN.findall(src)
    assert len(matches) >= 1, (
        "portability_router.py heeft geen HTTPException(451) raise in LawfulBasisMissingError blok"
    )
    assert len(_LOGGER_ERROR_PATTERN.findall(src)) >= 1, (
        "portability_router.py logt geen logger.error in LawfulBasisMissingError blok"
    )


def test_access_router_raises_451_in_lawful_basis_block():
    """access_router.py moet HTTPException(451) gooien IN except LawfulBasisMissingError."""
    src = Path("src/core/api/v1/gdpr_compliance/access_router.py").read_text(encoding="utf-8")
    matches = _HARD_BLOCK_PATTERN.findall(src)
    assert len(matches) >= 1, (
        "access_router.py heeft geen HTTPException(451) raise in LawfulBasisMissingError blok"
    )
    assert len(_LOGGER_ERROR_PATTERN.findall(src)) >= 1, (
        "access_router.py logt geen logger.error in LawfulBasisMissingError blok"
    )
