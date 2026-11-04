"""
User Domain Models - FASE 1.2 DDD
"""

from enum import Enum

from pydantic import EmailStr

from src.domains.shared import AggregateRoot


class UserRole(str, Enum):
    """User roles in the system"""

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User account status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class User(AggregateRoot):
    """
    User Aggregate Root
    Represents a user account in the system
    """

    email: EmailStr
    tenant_id: str
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.INACTIVE
    permissions: list[str] = []

    def activate(self) -> None:
        """Activate user account"""
        if self.status == UserStatus.DELETED:
            raise ValueError("Cannot activate deleted user")

        self.status = UserStatus.ACTIVE
        self.add_domain_event(
            {
                "type": "user.activated",
                "aggregate_id": self.id,
                "data": {"user_id": self.id, "email": str(self.email)},
            }
        )

    def suspend(self, reason: str) -> None:
        """Suspend user account"""
        self.status = UserStatus.SUSPENDED
        self.add_domain_event(
            {
                "type": "user.suspended",
                "aggregate_id": self.id,
                "data": {"user_id": self.id, "reason": reason},
            }
        )

    def grant_permission(self, permission: str) -> None:
        """Grant permission to user"""
        if permission not in self.permissions:
            self.permissions.append(permission)
            self.add_domain_event(
                {
                    "type": "user.permission_granted",
                    "aggregate_id": self.id,
                    "data": {"user_id": self.id, "permission": permission},
                }
            )
