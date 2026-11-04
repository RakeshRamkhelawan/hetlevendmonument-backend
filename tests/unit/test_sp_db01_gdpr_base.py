"""SP-DB-01: GDPR Base moet de hoofd-Base gebruiken, niet een eigen declarative_base().

Bewaakt dat gdpr_deletion.py altijd de gedeelde Base uit database.py importeert,
zodat Alembic autogenerate de GDPR-tabellen meeneemt.
"""

import ast
from pathlib import Path

_GDPR_FILE = Path(__file__).parent.parent.parent / "src" / "core" / "database" / "gdpr_deletion.py"


def test_gdpr_deletion_uses_shared_base() -> None:
    """gdpr_deletion.py mag geen eigen declarative_base() aanmaken."""
    src = _GDPR_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "declarative_base":
                raise AssertionError(
                    "gdpr_deletion.py roept declarative_base() aan -- "
                    "moet in plaats daarvan Base importeren uit src.core.database.database. "
                    "SP-DB-01: GDPR tabellen zijn anders onzichtbaar voor Alembic."
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr == "declarative_base":
                raise AssertionError(
                    "gdpr_deletion.py roept declarative_base() aan -- "
                    "moet Base importeren uit src.core.database.database. "
                    "SP-DB-01: GDPR tabellen zijn anders onzichtbaar voor Alembic."
                )


def test_gdpr_deletion_imports_base_from_database_module() -> None:
    """gdpr_deletion.py moet Base specifiek importeren uit src.core.database.database."""
    src = _GDPR_FILE.read_text(encoding="utf-8")
    assert "from src.core.database.database import" in src and "Base" in src, (
        "gdpr_deletion.py importeert Base niet uit src.core.database.database. "
        "SP-DB-01: voeg 'from src.core.database.database import Base' toe."
    )


def test_gdpr_deletion_report_applies_tenant_filter() -> None:
    """generate_deletion_report() moet tenant_id WHERE-clause toepassen (Backend Pattern 11)."""
    src = _GDPR_FILE.read_text(encoding="utf-8")
    assert "DeletionAudit.tenant_id ==" in src, (
        "generate_deletion_report() past geen WHERE-filter toe op tenant_id. "
        "Backend Pattern 11: tenant isolatie verplicht op elke list-methode. "
        "Fix: voeg .where(DeletionAudit.tenant_id == tenant_id) toe aan de query."
    )
