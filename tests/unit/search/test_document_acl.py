"""
Tests for Document ACL

Covers:
- Access rule creation
- Permission checking
- Owner access
- Public access
- Classification levels
- ACL modification
"""

import pytest

from src.core.search.document_acl import (
    AccessRule,
    Classification,
    DocumentACL,
    DocumentACLService,
    Permission,
    PrincipalType,
)


class TestAccessRule:
    """Test AccessRule dataclass."""

    def test_access_rule_creation(self):
        """Should create access rule with all fields."""
        rule = AccessRule(
            principal_type=PrincipalType.USER,
            principal_id=123,
            permission=Permission.READ,
        )

        assert rule.principal_type == PrincipalType.USER
        assert rule.principal_id == 123
        assert rule.permission == Permission.READ


class TestDocumentACL:
    """Test DocumentACL dataclass."""

    def test_acl_creation(self):
        """Should create ACL with required fields."""
        acl = DocumentACL(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
        )

        assert acl.document_id == "doc-123"
        assert acl.tenant_id == 1
        assert acl.owner_id == 100
        assert acl.is_public is True
        assert acl.classification == Classification.INTERNAL
        assert acl.access_rules == []

    def test_acl_add_rule(self):
        """Should add access rule to ACL."""
        acl = DocumentACL(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
        )

        rule = AccessRule(
            principal_type=PrincipalType.USER,
            principal_id=200,
            permission=Permission.READ,
        )

        acl.add_rule(rule)

        assert len(acl.access_rules) == 1
        assert acl.access_rules[0] == rule

    def test_acl_remove_rule(self):
        """Should remove rules for a principal."""
        acl = DocumentACL(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
        )

        rule = AccessRule(
            principal_type=PrincipalType.USER,
            principal_id=200,
            permission=Permission.READ,
        )

        acl.add_rule(rule)
        removed = acl.remove_rule(PrincipalType.USER, 200)

        assert removed is True
        assert len(acl.access_rules) == 0

    def test_acl_remove_nonexistent_rule(self):
        """Should return False when removing nonexistent rule."""
        acl = DocumentACL(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
        )

        removed = acl.remove_rule(PrincipalType.USER, 999)

        assert removed is False


class TestDocumentACLService:
    """Test DocumentACLService."""

    @pytest.fixture
    def service(self):
        """Create fresh ACL service."""
        return DocumentACLService()

    def test_create_acl(self, service):
        """Should create and store ACL."""
        acl = service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
            classification=Classification.CONFIDENTIAL,
        )

        assert acl.document_id == "doc-123"
        assert acl.tenant_id == 1
        assert acl.owner_id == 100
        assert acl.is_public is False
        assert acl.classification == Classification.CONFIDENTIAL

    def test_get_acl(self, service):
        """Should retrieve ACL by document ID."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
        )

        acl = service.get_acl("doc-123")

        assert acl is not None
        assert acl.document_id == "doc-123"

    def test_get_nonexistent_acl(self, service):
        """Should return None for nonexistent ACL."""
        acl = service.get_acl("nonexistent")

        assert acl is None

    def test_owner_always_has_access(self, service):
        """Owner should always have access regardless of rules."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=100,
            user_roles=["user"],
            permission=Permission.ADMIN,
        )

        assert has_access is True

    def test_public_read_access(self, service):
        """Public documents should allow READ to anyone."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=True,
            classification=Classification.PUBLIC,
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.READ,
        )

        assert has_access is True

    def test_public_no_write_access(self, service):
        """Public documents should not allow WRITE without explicit rule."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=True,
            classification=Classification.PUBLIC,
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.WRITE,
        )

        assert has_access is False

    def test_user_specific_rule(self, service):
        """Should check user-specific access rules."""
        acl = service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
        )

        acl.add_rule(
            AccessRule(
                principal_type=PrincipalType.USER,
                principal_id=200,
                permission=Permission.READ,
            )
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.READ,
        )

        assert has_access is True

    def test_permission_hierarchy_read(self, service):
        """WRITE permission should imply READ."""
        acl = service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
        )

        acl.add_rule(
            AccessRule(
                principal_type=PrincipalType.USER,
                principal_id=200,
                permission=Permission.WRITE,
            )
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.READ,
        )

        assert has_access is True

    def test_permission_hierarchy_write(self, service):
        """READ permission should not imply WRITE."""
        acl = service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
        )

        acl.add_rule(
            AccessRule(
                principal_type=PrincipalType.USER,
                principal_id=200,
                permission=Permission.READ,
            )
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.WRITE,
        )

        assert has_access is False

    def test_classification_public(self, service):
        """PUBLIC classification should allow all users."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=True,
            classification=Classification.PUBLIC,
        )

        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.READ,
        )

        assert has_access is True

    def test_classification_confidential(self, service):
        """CONFIDENTIAL classification should require manager role."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=True,
            classification=Classification.CONFIDENTIAL,
        )

        # User without manager role
        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.READ,
        )

        assert has_access is False

        # User with manager role
        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["manager"],
            permission=Permission.READ,
        )

        assert has_access is True

    def test_classification_restricted(self, service):
        """RESTRICTED classification should require admin role."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=True,
            classification=Classification.RESTRICTED,
        )

        # Manager without admin role
        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["manager"],
            permission=Permission.READ,
        )

        assert has_access is False

        # Admin role
        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["admin"],
            permission=Permission.READ,
        )

        assert has_access is True

    def test_share_document(self, service):
        """Should share document with multiple users."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
        )

        result = service.share_document(
            document_id="doc-123",
            user_ids=[200, 300],
            permission=Permission.READ,
            shared_by=100,
        )

        assert result is True

        # Check both users have access
        for user_id in [200, 300]:
            has_access = service.check_access(
                document_id="doc-123",
                user_id=user_id,
                user_roles=["user"],
                permission=Permission.READ,
            )
            assert has_access is True

    def test_share_document_non_owner(self, service):
        """Non-owner should not be able to share document."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
            is_public=False,
        )

        result = service.share_document(
            document_id="doc-123",
            user_ids=[200],
            permission=Permission.READ,
            shared_by=999,  # Non-owner
        )

        assert result is False

    def test_set_acl(self, service):
        """Should set ACL rules."""
        service.create_acl(
            document_id="doc-123",
            tenant_id=1,
            owner_id=100,
        )

        rules = [
            AccessRule(
                principal_type=PrincipalType.USER,
                principal_id=200,
                permission=Permission.WRITE,
            ),
        ]

        result = service.set_acl(
            document_id="doc-123",
            rules=rules,
            set_by=100,
        )

        assert result is True

        # Check new rule applies
        has_access = service.check_access(
            document_id="doc-123",
            user_id=200,
            user_roles=["user"],
            permission=Permission.WRITE,
        )
        assert has_access is True

    def test_get_accessible_documents(self, service):
        """Should get all documents accessible to user."""
        # Create documents
        for i in range(3):
            service.create_acl(
                document_id=f"doc-{i}",
                tenant_id=1,
                owner_id=100,
                is_public=False,
            )

        # Make doc-0 public
        acl = service.get_acl("doc-0")
        acl.is_public = True
        acl.classification = Classification.PUBLIC

        # Share doc-1 with user 200
        service.share_document(
            document_id="doc-1",
            user_ids=[200],
            permission=Permission.READ,
            shared_by=100,
        )

        # User 200 should access doc-0 and doc-1
        accessible = service.get_accessible_documents(
            user_id=200,
            user_roles=["user"],
            tenant_id=1,
        )

        assert "doc-0" in accessible
        assert "doc-1" in accessible
        assert "doc-2" not in accessible

    def test_filter_search_results(self, service):
        """Should filter search results by access rights."""
        # Create documents
        for i in range(3):
            service.create_acl(
                document_id=f"doc-{i}",
                tenant_id=1,
                owner_id=100,
                is_public=False,
            )

        # Make doc-0 public
        acl = service.get_acl("doc-0")
        acl.is_public = True
        acl.classification = Classification.PUBLIC

        # Share doc-1 with user 200
        service.share_document(
            document_id="doc-1",
            user_ids=[200],
            permission=Permission.READ,
            shared_by=100,
        )

        # Filter results
        search_results = ["doc-0", "doc-1", "doc-2"]
        filtered = service.filter_search_results(
            document_ids=search_results,
            user_id=200,
            user_roles=["user"],
        )

        assert "doc-0" in filtered
        assert "doc-1" in filtered
        assert "doc-2" not in filtered
