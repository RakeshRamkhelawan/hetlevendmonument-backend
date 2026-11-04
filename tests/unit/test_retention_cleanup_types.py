"""TDD tests for retention_cleanup type fixes (B2.5).

DataCategory must have USER_DATA, ACTIVITY_LOGS, AI_INTERACTIONS, DOCUMENTS, ANALYTICS.
"""


def test_data_category_enum_members_exist():
    """DataCategory must include all members used by retention_cleanup_job."""
    from src.core.governance.retention_cleanup import DataCategory

    assert hasattr(DataCategory, "USER_DATA")
    assert hasattr(DataCategory, "ACTIVITY_LOGS")
    assert hasattr(DataCategory, "AI_INTERACTIONS")
    assert hasattr(DataCategory, "DOCUMENTS")
    assert hasattr(DataCategory, "ANALYTICS")
    assert DataCategory.USER_DATA.value == "user_data"
    assert DataCategory.ACTIVITY_LOGS.value == "activity_logs"
