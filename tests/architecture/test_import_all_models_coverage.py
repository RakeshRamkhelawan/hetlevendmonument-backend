"""Architecture test: import_all_models.py must cover the company layer.

Without this coverage, Base.metadata.create_all() in the integration test conftest
will NOT create the company layer tables (goals, company_templates, external_agents,
pack_activation_audit_logs), causing "relation X does not exist" errors in ~45 tests.

Root cause documented in: docs/backend/features/BE-TST-001-import-all-models-coverage.md
"""


def test_company_layer_tables_in_base_metadata() -> None:
    """After importing import_all_models, company layer tables must be in Base.metadata.

    If this test fails, add the missing import to src/core/database/import_all_models.py.
    """
    import src.core.database.import_all_models  # noqa: F401

    from src.core.database.database import Base

    registered = set(Base.metadata.tables.keys())
    required = {
        "goals",
        "company_templates",
        "external_agents",
        "pack_activation_audit_logs",
        "companies",
        "departments",
    }
    missing = required - registered
    assert not missing, (
        f"Company layer tables missing from Base.metadata: {missing}. "
        "Add the model import to src/core/database/import_all_models.py."
    )
