"""AVG-inzage en -export lezen auditregels via de gedeelde filter `audit_rows_about_user`.

ADR-039 vervolg: `user_id` van een auditregel is de ACTOR; bij een rolwijziging staat de persoon die
de rol kreeg of verloor in `resource`. Wie in een inzage- of exportpad zelf `AuditLog.user_id ==
<persoon>` schrijft, laat die persoon zijn rolwijzigingen niet zien. Gedrag met een echte database:
`tests/integration/test_gdpr_inzage_vindt_rolwijzigingen_over_de_persoon.py`.

Wat bewaakt wordt (de benoemde verzameling is `LEZERS`, een mutatie per element hieronder):
  1. Elke lezer in `LEZERS` roept `audit_rows_about_user(...)` aan.
  2. Nergens in `src/` staat een vergelijking `AuditLog.user_id == ...` behalve in de helper zelf
     (`src/core/governance/audit.py`): een nieuw inzagepad dat de filter omzeilt valt hier op.

Mutatiebewijs (2026-10-10; kopie als terugweg, nooit `git checkout --`):
  ROOD:
    de aanroep in access_router.py vervangen door `AuditLog.user_id == user_id`   -> test 1 en 2
    idem in portability_router.py                                                  -> test 1 en 2
    idem in dsar_service.py                                                        -> test 1 en 2
    een nieuw bestand met `select(AuditLog).where(AuditLog.user_id == 1)`          -> test 2
  GROEN, legitiem blijft toegestaan:
    `AuditLog.user_id` als kolom in een select-lijst of order_by (geen vergelijking) -> test 2
    een extra lezer die de helper WEL gebruikt                                     -> test 1 en 2
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
HELPER = SRC / "core" / "governance" / "audit.py"

LEZERS = (
    SRC / "core" / "api" / "v1" / "gdpr_compliance" / "access_router.py",
    SRC / "core" / "api" / "v1" / "gdpr_compliance" / "portability_router.py",
    SRC / "core" / "governance" / "dsar_service.py",
)


def _boom(pad: Path) -> ast.AST:
    return ast.parse(pad.read_text(encoding="utf-8"))


def _roept_helper_aan(pad: Path) -> bool:
    for knoop in ast.walk(_boom(pad)):
        if isinstance(knoop, ast.Call):
            f = knoop.func
            naam = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            if naam == "audit_rows_about_user":
                return True
    return False


def _vergelijkt_audit_user_id(pad: Path) -> list[int]:
    """Regels met een VERGELIJKING op `AuditLog.user_id` (een select-lijst of order_by telt niet)."""
    regels: list[int] = []
    for knoop in ast.walk(_boom(pad)):
        if not isinstance(knoop, ast.Compare):
            continue
        for zijde in [knoop.left, *knoop.comparators]:
            if (
                isinstance(zijde, ast.Attribute)
                and zijde.attr == "user_id"
                and isinstance(zijde.value, ast.Name)
                and zijde.value.id == "AuditLog"
            ):
                regels.append(knoop.lineno)
    return regels


def test_the_readers_exist() -> None:
    """Een verplaatst bestand laat de tests hieronder groen zonder iets te meten."""
    ontbreekt = [str(p.relative_to(REPO)) for p in LEZERS if not p.is_file()]
    assert not ontbreekt, f"lezer niet gevonden: {ontbreekt}"


def test_every_reader_uses_the_shared_audit_filter() -> None:
    zonder = [str(p.relative_to(REPO)) for p in LEZERS if not _roept_helper_aan(p)]
    assert not zonder, (
        f"Inzage/export zonder `audit_rows_about_user`: {zonder}. Een rolwijziging OVER de persoon "
        "staat onder het user_id van de actor en wordt dan niet gevonden (AVG art. 15/20)."
    )


def test_no_code_outside_the_helper_compares_audit_log_user_id() -> None:
    gevonden: dict[str, list[int]] = {}
    for pad in SRC.rglob("*.py"):
        if pad == HELPER:
            continue
        regels = _vergelijkt_audit_user_id(pad)
        if regels:
            gevonden[str(pad.relative_to(REPO))] = regels
    assert not gevonden, (
        f"`AuditLog.user_id == ...` buiten de helper: {gevonden}. Gebruik "
        "`audit_rows_about_user(user_id)` voor inzage en export (ADR-039)."
    )
