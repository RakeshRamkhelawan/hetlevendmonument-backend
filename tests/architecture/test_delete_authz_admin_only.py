"""Architecture guard -- tenant-wide delete-all is admin-only (GDPR-001).

Dag 8 dichtte een P0: de tenant-brede erasure-endpoint (`POST /api/gdpr/delete-all`,
`delete_tenant_data`) checkte de admin-rol alleen op de HARD-tak; de SOFT-tak was
alleen door `confirmation_code == tenant_id` (JWT-afgeleid, geen geheim) beschermd,
zodat een niet-admin de hele tenant kon soft-deleten + een purge inplannen.

Deze guard faalt als die fix regresseert: de admin-check MOET vóór de SOFT/HARD-
vertakking staan, zodat beide takken hem vereisen. Regressie-guard voor SP dag 8
BE-GDPR-001. Alleen stdlib (pathlib, re) -- geen src-imports.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ERASURE_ROUTER = (
    _REPO_ROOT / "src" / "core" / "api" / "v1" / "gdpr_compliance" / "erasure_router.py"
)


def test_delete_tenant_data_requires_admin_before_branching() -> None:
    """delete_tenant_data checkt de admin-rol VOOR de SOFT/HARD-vertakking. [BE-GDPR-001]

    Guard tegen de dag-8 P0-regressie: als de admin-check verdwijnt of achter de
    SOFT-tak belandt, kan een niet-admin de tenant soft-deleten.
    """
    assert _ERASURE_ROUTER.exists(), (
        f"Bestand niet gevonden: {_ERASURE_ROUTER}. Pad incorrect of bestand verplaatst."
    )
    source = _ERASURE_ROUTER.read_text(encoding="utf-8")

    func_match = re.search(
        r"async def delete_tenant_data\b.*?(?=\nasync def |\ndef |\Z)",
        source,
        re.DOTALL,
    )
    assert func_match is not None, (
        "BE-GDPR-001 [REGRESSION]: delete_tenant_data niet gevonden in "
        f"{_ERASURE_ROUTER.relative_to(_REPO_ROOT)}. De tenant-brede erasure-endpoint "
        "moet bestaan EN de admin-rol afdwingen voor beide delete-types."
    )
    body = func_match.group(0)

    admin_check = re.search(r"""["']admin["']\s+not\s+in\s+current_user\.roles""", body)
    assert admin_check is not None, (
        "BE-GDPR-001 [REGRESSION]: delete_tenant_data dwingt de admin-rol niet meer af "
        "('admin' not in current_user.roles ontbreekt). Een niet-admin kan de HELE tenant "
        "wissen (privilege-escalatie). Rol MOET uit de geverifieerde JWT komen, nooit uit "
        "body/param. Fixt door SP dag 8 BE-GDPR-001."
    )

    soft_branch = re.search(r"request\.delete_type\s*==\s*DeleteType\.SOFT", body)
    assert soft_branch is not None, (
        "BE-GDPR-001: de SOFT/HARD-vertakking (DeleteType.SOFT) is niet gevonden in "
        "delete_tenant_data -- structuur gewijzigd; controleer de guard."
    )

    assert admin_check.start() < soft_branch.start(), (
        "BE-GDPR-001 [REGRESSION]: de admin-check staat NA de SOFT-vertakking. Dat was exact "
        "de dag-8 P0: de SOFT-tak werd niet door admin beschermd. Zet de admin-check VOOR de "
        "'if request.delete_type == DeleteType.SOFT'-vertakking zodat SOFT en HARD hem beide "
        "vereisen. Fixt door SP dag 8 BE-GDPR-001."
    )
