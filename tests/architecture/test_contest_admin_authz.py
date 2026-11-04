"""Architecture guard -- contest admin-flow is admin-only (GDPR art. 22).

Dag 7 (BE-A22-001) voegde de contest admin-queue + resolve toe: een gebruiker die
een geautomatiseerde beslissing aanvecht (GDPR art. 22) wordt door een tenant-admin
afgehandeld. Zowel het inzien van de queue (`list_contests`) als het afhandelen
(`resolve_contest`) MOET admin-only zijn, anders kan een niet-admin andermans
contests inzien/afhandelen.

Deze guard faalt als die admin-check verdwijnt. Regressie-guard voor SP dag 7
BE-A22-001. Alleen stdlib (pathlib, re) -- geen src-imports.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUDIT_ENDPOINTS = _REPO_ROOT / "src" / "core" / "copilot" / "api" / "audit_endpoints.py"


def _func_body(name: str) -> str:
    assert _AUDIT_ENDPOINTS.exists(), (
        f"Bestand niet gevonden: {_AUDIT_ENDPOINTS}. Pad incorrect of bestand verplaatst."
    )
    source = _AUDIT_ENDPOINTS.read_text(encoding="utf-8")
    match = re.search(
        rf"async def {name}\b.*?(?=\n@router|\nasync def |\ndef |\Z)",
        source,
        re.DOTALL,
    )
    assert match is not None, (
        f"BE-A22-001 [REGRESSION]: {name} niet gevonden in "
        f"{_AUDIT_ENDPOINTS.relative_to(_REPO_ROOT)}. De contest-endpoint moet bestaan "
        "EN de admin-rol afdwingen."
    )
    return match.group(0)


def test_list_contests_requires_admin() -> None:
    """De contest-queue is admin-only. [BE-A22-001]"""
    body = _func_body("list_contests")
    assert "_is_tenant_admin" in body, (
        "BE-A22-001 [REGRESSION]: list_contests dwingt de admin-rol niet meer af "
        "(_is_tenant_admin ontbreekt). Een niet-admin kan dan de contest-queue van de "
        "tenant inzien. Fixt door SP dag 7 BE-A22-001."
    )


def test_resolve_contest_requires_admin() -> None:
    """Een contest afhandelen is admin-only. [BE-A22-001]"""
    body = _func_body("resolve_contest")
    assert "_is_tenant_admin" in body, (
        "BE-A22-001 [REGRESSION]: resolve_contest dwingt de admin-rol niet meer af "
        "(_is_tenant_admin ontbreekt). Een niet-admin kan dan een aangevochten beslissing "
        "afhandelen. Fixt door SP dag 7 BE-A22-001."
    )
