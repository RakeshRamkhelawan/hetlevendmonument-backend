"""
User Management router composite (ADR-033 Laag 2).

Provides full CRUD operations for user management within tenants.
- Tenant admins can manage users in their tenant
- Superusers can manage all users
- Regular users can only view/update their own profile
"""

from fastapi import APIRouter

from src.core.api.v1.users.me_router import me_router
from src.core.api.v1.users.users_detail_router import users_detail_router
from src.core.api.v1.users.users_list_router import users_list_router

router = APIRouter(prefix="/users", tags=["User Management"])

router.include_router(me_router)
router.include_router(users_list_router)
router.include_router(users_detail_router)
