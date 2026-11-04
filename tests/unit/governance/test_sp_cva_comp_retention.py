"""COMP-003: CVA conversations moeten in retention_cleanup zitten.

GDPR Art. 17 -- Right to Erasure: CVA conversation data moet door retention cleanup
verwijderd kunnen worden. Tests zijn ROOD totdat Fix C is geimplementeerd.
"""


class TestCVARetentionTables:
    """CVA conversation tabellen moeten in de retention allowlist staan."""

    def test_conversations_in_allowed_tables(self):
        """'conversations' tabel moet in _RETENTION_ALLOWED_TABLES staan (SP-CVA-COMP-003)."""
        from src.core.governance.retention_cleanup import _RETENTION_ALLOWED_TABLES

        assert "conversations" in _RETENTION_ALLOWED_TABLES, (
            "'conversations' ontbreekt in _RETENTION_ALLOWED_TABLES. "
            "Vereist voor GDPR Art. 17 retention cleanup (SP-CVA-COMP-003)."
        )

    def test_conversation_messages_in_allowed_tables(self):
        """'conversation_messages' tabel moet in _RETENTION_ALLOWED_TABLES staan."""
        from src.core.governance.retention_cleanup import _RETENTION_ALLOWED_TABLES

        assert "conversation_messages" in _RETENTION_ALLOWED_TABLES, (
            "'conversation_messages' ontbreekt in _RETENTION_ALLOWED_TABLES. "
            "Vereist voor GDPR Art. 17 retention cleanup (SP-CVA-COMP-003)."
        )

    def test_cva_conversations_in_allowed_tables(self):
        """'cva_conversations' tabel moet in _RETENTION_ALLOWED_TABLES staan."""
        from src.core.governance.retention_cleanup import _RETENTION_ALLOWED_TABLES

        assert "cva_conversations" in _RETENTION_ALLOWED_TABLES, (
            "'cva_conversations' ontbreekt in _RETENTION_ALLOWED_TABLES. "
            "Vereist voor GDPR Art. 17 retention cleanup (SP-CVA-COMP-003)."
        )


class TestCVADataCategory:
    """DataCategory enum moet CVA-specifieke categorieen bevatten."""

    def test_data_category_cva_conversation_exists(self):
        """DataCategory.CVA_CONVERSATION moet bestaan (SP-CVA-COMP-003)."""
        from src.core.governance.retention_cleanup import DataCategory

        cva_cat = getattr(DataCategory, "CVA_CONVERSATION", None)
        assert cva_cat is not None, (
            "DataCategory.CVA_CONVERSATION ontbreekt. "
            "Vereist voor GDPR Art. 17 data inventory (SP-CVA-COMP-003)."
        )
        assert cva_cat.value == "cva_conversation"

    def test_data_category_cva_message_exists(self):
        """DataCategory.CVA_MESSAGE moet bestaan (SP-CVA-COMP-003)."""
        from src.core.governance.retention_cleanup import DataCategory

        assert hasattr(DataCategory, "CVA_MESSAGE"), (
            "DataCategory.CVA_MESSAGE ontbreekt. "
            "Vereist voor GDPR Art. 17 data inventory (SP-CVA-COMP-003)."
        )

    def test_data_category_cva_session_exists(self):
        """DataCategory.CVA_SESSION moet bestaan (SP-CVA-COMP-003)."""
        from src.core.governance.retention_cleanup import DataCategory

        assert hasattr(DataCategory, "CVA_SESSION"), (
            "DataCategory.CVA_SESSION ontbreekt. "
            "Vereist voor GDPR Art. 17 data inventory (SP-CVA-COMP-003)."
        )

    def test_cva_conversation_mapped_in_table_info(self):
        """CVA_CONVERSATION moet een tabel-mapping hebben in _get_table_info()."""
        from unittest.mock import AsyncMock

        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionCleanupService,
        )

        mock_db = AsyncMock()
        svc = RetentionCleanupService(db=mock_db, tenant_id=1)

        cva_cat = getattr(DataCategory, "CVA_CONVERSATION", None)
        assert cva_cat is not None, "DataCategory.CVA_CONVERSATION ontbreekt -- Fix C vereist."
        info = svc._get_table_info(cva_cat)  # type: ignore[arg-type]
        assert info["table"] == "conversations", (
            "CVA_CONVERSATION mapping retourneert verkeerde tabel. Verwacht: 'conversations'."
        )
        assert info["date_column"] == "updated_at"
        assert info["tenant_column"] == "tenant_id"
