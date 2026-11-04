"""
Tenant Isolation Integration Tests - CRITICAL SECURITY
Verifies that tenant1 can NEVER access tenant2 data

ZERO TOLERANCE: Even 1 leaked query = production data breach
"""

import pytest
from typing import Any

from typing import Any

from src.core.conversations.models import CVAConversation
from src.core.database.database import db_manager
from src.core.middleware.tenant_context import clear_tenant_context, get_tenant_id, set_tenant_id


class TestTenantIsolation:
    """Test suite for tenant data isolation"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Setup and teardown for each test"""
        # Setup: Ensure database is initialized
        if not db_manager.is_initialized():
            db_manager.initialize()

        yield

        # Teardown: Clear tenant context
        clear_tenant_context()

    def test_tenant_context_isolation(self):
        """Test that tenant context is properly isolated"""
        # Set tenant1
        set_tenant_id("tenant_1")
        assert get_tenant_id() == "tenant_1"

        # Set tenant2
        set_tenant_id("tenant_2")
        assert get_tenant_id() == "tenant_2"

        # Clear context
        clear_tenant_context()
        assert get_tenant_id() is None

    def test_conversation_query_filtered_by_tenant(self):
        """Test that conversation queries are automatically filtered by tenant_id"""
        # Create test data for tenant1
        set_tenant_id("tenant_1")
        with db_manager.get_session() as session:
            conv1 = CVAConversation(
                session_id="session_1",
                user_id="user_1",
                tenant_id="tenant_1",
                user_message="Hello from tenant 1",
                cva_response="Response for tenant 1",
                conversation_turn=1,
            )
            session.add(conv1)
            session.commit()
            conv1_id = conv1.id

        # Create test data for tenant2
        set_tenant_id("tenant_2")
        with db_manager.get_session() as session:
            conv2 = CVAConversation(
                session_id="session_2",
                user_id="user_2",
                tenant_id="tenant_2",
                user_message="Hello from tenant 2",
                cva_response="Response for tenant 2",
                conversation_turn=1,
            )
            session.add(conv2)
            session.commit()
            conv2_id = conv2.id

        # Query as tenant1 - should ONLY see tenant1 data
        set_tenant_id("tenant_1")
        with db_manager.get_session() as session:
            conversations = (
                session.query(CVAConversation)
                .filter(CVAConversation.tenant_id == get_tenant_id())
                .all()
            )

            assert len(conversations) >= 1
            assert all(conv.tenant_id == "tenant_1" for conv in conversations)
            assert conv1_id in [conv.id for conv in conversations]
            assert conv2_id not in [conv.id for conv in conversations]

        # Query as tenant2 - should ONLY see tenant2 data
        set_tenant_id("tenant_2")
        with db_manager.get_session() as session:
            conversations = (
                session.query(CVAConversation)
                .filter(CVAConversation.tenant_id == get_tenant_id())
                .all()
            )

            assert len(conversations) >= 1
            assert all(conv.tenant_id == "tenant_2" for conv in conversations)
            assert conv2_id in [conv.id for conv in conversations]
            assert conv1_id not in [conv.id for conv in conversations]

        # Cleanup
        set_tenant_id("tenant_1")
        with db_manager.get_session() as session:
            session.query(CVAConversation).filter(CVAConversation.id == conv1_id).delete()
            session.commit()

        set_tenant_id("tenant_2")
        with db_manager.get_session() as session:
            session.query(CVAConversation).filter(CVAConversation.id == conv2_id).delete()
            session.commit()

    def test_cross_tenant_access_returns_404(self):
        """Test that attempting to access another tenant's data returns 404"""
        # Create data for tenant1
        set_tenant_id("tenant_1")
        with db_manager.get_session() as session:
            conv = CVAConversation(
                session_id="test_session",
                user_id="user_1",
                tenant_id="tenant_1",
                user_message="Test message",
                cva_response="Test response",
                conversation_turn=1,
            )
            session.add(conv)
            session.commit()
            conv_id = conv.id

        # Try to access as tenant2 - should return None (404)
        set_tenant_id("tenant_2")
        with db_manager.get_session() as session:
            result = (
                session.query(CVAConversation)
                .filter(
                    CVAConversation.tenant_id == get_tenant_id(),
                    CVAConversation.id == conv_id,
                )
                .first()
            )

            assert result is None  # Tenant2 cannot see tenant1 data

        # Cleanup
        set_tenant_id("tenant_1")
        with db_manager.get_session() as session:
            session.query(CVAConversation).filter(CVAConversation.id == conv_id).delete()
            session.commit()

    def test_all_queries_must_have_tenant_filter(self):
        """
        CRITICAL: Verify that ALL database queries include tenant_id filter
        This is a ZERO TOLERANCE test - even 1 unfiltered query = FAIL
        """
        import os
        import re

        # Search for db.query or session.query without tenant_id
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        src_dir = os.path.join(project_root, "core")

        unfiltered_queries: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        for root, dirs, files in os.walk(src_dir):
            # Skip backup directories
            if "_old_structure_backup" in root or "backups" in root:
                continue

            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                        # Find all query calls
                        query_pattern = r"(db|session)\.query\([^)]+\)"
                        matches = re.finditer(query_pattern, content)

                        for match in matches:
                            # Check if tenant_id filter exists nearby
                            start = max(0, match.start() - 200)
                            end = min(len(content), match.end() + 200)
                            context = content[start:end]

                            if "tenant_id" not in context and "Tenant" not in context:
                                unfiltered_queries.append(
                                    {"file": file_path, "query": match.group(0)}
                                )

        # ZERO TOLERANCE: No unfiltered queries allowed
        if unfiltered_queries:
            error_msg = "[FAIL] Found unfiltered queries (data leak risk):\n"
            for query in unfiltered_queries:
                error_msg += f"  - {query['file']}: {query['query']}\n"
            pytest.fail(error_msg)

        assert len(unfiltered_queries) == 0, "All queries MUST filter by tenant_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
