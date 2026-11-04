"""
FocusBuilder KRITIEK backlog -- falende architecture tests.

Drie productieblokkerende bevindingen uit FocusBuilder-audit 2026-06-18.
Tests zijn ROOD totdat de backlog-items gefixd zijn (zie docs/audits/FOCUSBUILDER_AUDIT_2026-06-18.md).

TODO(SP-FB-001): fix alle drie KRITIEK-bevindingen
"""

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_ALEMBIC_DIR = _REPO_ROOT / "src" / "alembic" / "versions"
_FLOWS_SERVICE = _REPO_ROOT / "src" / "domains" / "flows" / "service.py"
_FLOWS_MODELS = _REPO_ROOT / "src" / "domains" / "flows" / "models.py"
_LEGACY_MODELS = _REPO_ROOT / "src" / "core" / "focus_builder" / "models.py"


@pytest.mark.architecture
def test_flows_table_has_alembic_migration() -> None:
    """TODO(SP-FB-001): flows-tabel MOET een Alembic-migratie hebben.

    KRITIEK-2: `flows`-tabel bestaat niet in de database. Geen enkele migratie
    roept op.create_table aan voor 'flows' of 'focus_builder_pieces_cache'.
    Audit: docs/audits/FOCUSBUILDER_AUDIT_2026-06-18.md sectie 2.2.
    """
    assert _ALEMBIC_DIR.is_dir(), f"alembic/versions not found at {_ALEMBIC_DIR}"

    tables_created: set[str] = set()
    for migration in _ALEMBIC_DIR.glob("*.py"):
        if "__pycache__" in str(migration):
            continue
        text = migration.read_text(encoding="utf-8")
        if re.search(r'create_table\s*\(\s*["\']flows["\']', text):
            tables_created.add("flows")
        if re.search(r'create_table\s*\(\s*["\']focus_builder_pieces_cache["\']', text):
            tables_created.add("focus_builder_pieces_cache")

    missing = {"flows", "focus_builder_pieces_cache"} - tables_created
    assert not missing, (
        f"Geen Alembic-migratie gevonden voor tabellen: {missing}. "
        "FocusBuilder is non-functioneel zonder deze migraties. "
        "Fix: schrijf een migratie voor src/domains/flows/models.py. "
        "SP-FB-001 backlog."
    )


@pytest.mark.architecture
def test_focus_builder_service_no_ap_client_in_init() -> None:
    """TODO(SP-FB-001): ActivePiecesClient mag NIET in __init__ worden aangemaakt.

    KRITIEK-1: FocusBuilderService.__init__ roept ActivePiecesClient() aan die
    direct een ValueError gooit als AP-credentials ontbreken. Dit raakt ALLE
    endpoints inclusief read-only GET /flows.
    Audit: docs/audits/FOCUSBUILDER_AUDIT_2026-06-18.md sectie 2.2.
    """
    assert _FLOWS_SERVICE.exists(), f"FocusBuilderService niet gevonden: {_FLOWS_SERVICE}"
    tree = ast.parse(_FLOWS_SERVICE.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or "FocusBuilderService" not in node.name:
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
                continue
            # Zoek naar ActivePiecesClient() aanroep in __init__
            for subnode in ast.walk(item):
                if isinstance(subnode, ast.Call):
                    func = subnode.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else (func.attr if isinstance(func, ast.Attribute) else "")
                    )
                    if "ActivePiecesClient" in name:
                        pytest.fail(
                            f"{_FLOWS_SERVICE.name}.__init__ instantieert ActivePiecesClient() "
                            "direct -- gooit ValueError als AP-credentials ontbreken. "
                            "Fix: lazy property of factory methode gebruiken. "
                            "SP-FB-001 backlog."
                        )


@pytest.mark.architecture
def test_no_duplicate_focus_builder_pieces_cache_model() -> None:
    """TODO(SP-FB-001): focus_builder_pieces_cache mag maar door EEN ORM-model worden beheerd.

    KRITIEK-3: Twee modellen claimen dezelfde tabelnaam met verschillende kolommen.
    src/core/focus_builder/models.py:FocusBuilderPieceCache en
    src/domains/flows/models.py:PiecesCacheMetadata -- mapper-conflict bij import.
    Audit: docs/audits/FOCUSBUILDER_AUDIT_2026-06-18.md sectie 2.2.
    """
    table_name = "focus_builder_pieces_cache"
    owners: list[str] = []

    assert any(c.exists() for c in (_FLOWS_MODELS, _LEGACY_MODELS)), (
        f"Geen van beide modelbestanden bestaat nog: {_FLOWS_MODELS}, {_LEGACY_MODELS}. "
        "Allebei hernoemd/verplaatst? Dan blijft `owners` leeg en slaagt deze test "
        "triviaal, terwijl een mapper-conflict elders (nieuwe bestanden die dezelfde "
        f"tabelnaam '{table_name}' claimen) onopgemerkt zou blijven."
    )

    for candidate in [_FLOWS_MODELS, _LEGACY_MODELS]:
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8")
        if f'"{table_name}"' in text or f"'{table_name}'" in text:
            owners.append(str(candidate.relative_to(_REPO_ROOT)))

    assert len(owners) <= 1, (
        f"Tabelnaam '{table_name}' geclaimd door meerdere ORM-modellen: {owners}. "
        "SQLAlchemy mapper-conflict -- de laatste import wint, kolommen komen niet overeen. "
        "Fix: verwijder src/core/focus_builder/models.py (legacy). "
        "SP-FB-001 backlog."
    )
