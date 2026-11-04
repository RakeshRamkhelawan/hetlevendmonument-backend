"""
Document Access Control Lists (ACL)

Provides:
- Document-level access control
- Role-based and user-based permissions
- Classification levels
- Tenant isolation
"""

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


class Permission(enum.Enum):
    """Document permissions."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class PrincipalType(enum.Enum):
    """Principal types for access rules."""

    USER = "user"
    ROLE = "role"
    GROUP = "group"


class Classification(enum.Enum):
    """Document classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class AccessRule:
    """Single access rule."""

    principal_type: PrincipalType
    principal_id: int
    permission: Permission


@dataclass
class DocumentACL:
    """Access control list for a document."""

    document_id: str
    tenant_id: int
    owner_id: int
    access_rules: list[AccessRule] = field(default_factory=list)
    is_public: bool = True
    classification: Classification = Classification.INTERNAL

    def add_rule(self, rule: AccessRule) -> None:
        """Add an access rule."""
        self.access_rules.append(rule)

    def remove_rule(self, principal_type: PrincipalType, principal_id: int) -> bool:
        """Remove rules for a principal."""
        original_len = len(self.access_rules)
        self.access_rules = [
            r
            for r in self.access_rules
            if not (r.principal_type == principal_type and r.principal_id == principal_id)
        ]
        return len(self.access_rules) < original_len


class DocumentACLService:
    """Service for managing document ACLs."""

    # Minimum role required for each classification
    CLASSIFICATION_MIN_ROLE = {
        Classification.PUBLIC: None,
        Classification.INTERNAL: "user",
        Classification.CONFIDENTIAL: "manager",
        Classification.RESTRICTED: "admin",
    }

    def __init__(self) -> None:
        self._acls: dict[str, DocumentACL] = {}

    def create_acl(
        self,
        document_id: str,
        tenant_id: int,
        owner_id: int,
        is_public: bool = True,
        classification: Classification = Classification.INTERNAL,
    ) -> DocumentACL:
        """Create ACL for a new document."""
        acl = DocumentACL(
            document_id=document_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            is_public=is_public,
            classification=classification,
        )
        self._acls[document_id] = acl
        return acl

    def get_acl(self, document_id: str) -> DocumentACL | None:
        """Get ACL for a document."""
        return self._acls.get(document_id)

    def check_access(
        self,
        document_id: str,
        user_id: int,
        user_roles: list[str],
        permission: Permission,
    ) -> bool:
        """
        Check if user has access to document.

        Args:
            document_id: Document ID
            user_id: User ID
            user_roles: User's roles
            permission: Requested permission

        Returns:
            True if access allowed
        """
        acl = self._acls.get(document_id)
        if not acl:
            return False

        # Owner always has access
        if user_id == acl.owner_id:
            return True

        # Check public access (READ only)
        if acl.is_public and permission == Permission.READ:
            # Still need to check classification
            return self._check_classification(acl.classification, user_roles)

        # Check explicit rules
        for rule in acl.access_rules:
            # Check user-specific rule
            if rule.principal_type == PrincipalType.USER and rule.principal_id == user_id:
                if self._permission_sufficient(rule.permission, permission):
                    return True

            # Check role-based rule
            if rule.principal_type == PrincipalType.ROLE:
                role_name = self._get_role_name(rule.principal_id)
                if role_name in user_roles:
                    if self._permission_sufficient(rule.permission, permission):
                        return True

        return False

    def _check_classification(self, classification: Classification, user_roles: list[str]) -> bool:
        """Check if user meets classification requirements."""
        min_role = self.CLASSIFICATION_MIN_ROLE.get(classification)
        if min_role is None:
            return True

        # Simple role hierarchy
        role_hierarchy = ["user", "manager", "admin"]
        if min_role not in role_hierarchy:
            return True

        min_level = role_hierarchy.index(min_role)

        for role in user_roles:
            if role in role_hierarchy:
                if role_hierarchy.index(role) >= min_level:
                    return True

        return False

    def _permission_sufficient(self, has: Permission, needs: Permission) -> bool:
        """Check if permission level is sufficient."""
        hierarchy = {Permission.READ: 0, Permission.WRITE: 1, Permission.ADMIN: 2}
        return hierarchy.get(has, 0) >= hierarchy.get(needs, 0)

    def _get_role_name(self, role_id: int) -> str:
        """Get role name from ID (placeholder)."""
        # Would query database in real implementation
        role_map = {1: "user", 2: "manager", 3: "admin"}
        return role_map.get(role_id, "user")

    def set_acl(
        self,
        document_id: str,
        rules: list[AccessRule],
        set_by: int,
    ) -> bool:
        """
        Set ACL rules (admin/owner only).

        Args:
            document_id: Document ID
            rules: New access rules
            set_by: User ID making the change

        Returns:
            True if successful
        """
        acl = self._acls.get(document_id)
        if not acl:
            return False

        # Check if user can modify ACL
        if set_by != acl.owner_id:
            # Check if user has ADMIN permission
            has_admin = any(
                r.principal_type == PrincipalType.USER
                and r.principal_id == set_by
                and r.permission == Permission.ADMIN
                for r in acl.access_rules
            )
            if not has_admin:
                return False

        acl.access_rules = rules
        return True

    def share_document(
        self,
        document_id: str,
        user_ids: list[int],
        permission: Permission,
        shared_by: int,
    ) -> bool:
        """
        Share document with users.

        Args:
            document_id: Document ID
            user_ids: Users to share with
            permission: Permission level
            shared_by: User sharing the document

        Returns:
            True if successful
        """
        acl = self._acls.get(document_id)
        if not acl:
            return False

        # Only owner or admin can share
        if shared_by != acl.owner_id:
            return False

        for user_id in user_ids:
            # Remove existing rules for this user
            acl.remove_rule(PrincipalType.USER, user_id)

            # Add new rule
            acl.add_rule(
                AccessRule(
                    principal_type=PrincipalType.USER,
                    principal_id=user_id,
                    permission=permission,
                )
            )

        return True

    def get_accessible_documents(
        self,
        user_id: int,
        user_roles: list[str],
        tenant_id: int,
        permission: Permission = Permission.READ,
    ) -> list[str]:
        """
        Get all documents accessible to user.

        Args:
            user_id: User ID
            user_roles: User's roles
            tenant_id: Tenant ID
            permission: Required permission

        Returns: List[Any] of document IDs  # TODO(TYPE): replace Any with concrete type
        """
        accessible: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for doc_id, acl in self._acls.items():
            if acl.tenant_id != tenant_id:
                continue

            if self.check_access(doc_id, user_id, user_roles, permission):
                accessible.append(doc_id)

        return accessible

    def filter_search_results(
        self,
        document_ids: list[str],
        user_id: int,
        user_roles: list[str],
        permission: Permission = Permission.READ,
    ) -> list[str]:
        """
        Filter search results by access rights.

        Args:
            document_ids: Candidate document IDs
            user_id: User ID
            user_roles: User's roles
            permission: Required permission

        Returns:
            Filtered list of accessible document IDs
        """
        return [
            doc_id
            for doc_id in document_ids
            if self.check_access(doc_id, user_id, user_roles, permission)
        ]
