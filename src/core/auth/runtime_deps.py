"""Auth facade voor agent_runtime laag.

Re-exporteert auth-primitives die agent_runtime consumers nodig hebben.
Stable import point: interne auth module reorganisatie vereist geen
wijzigingen in agent_runtime bestanden.
"""

from .auth_service import UserResponse
from .dependencies import get_current_user, is_admin, is_tenant_admin

__all__ = ["UserResponse", "get_current_user", "is_admin", "is_tenant_admin"]
