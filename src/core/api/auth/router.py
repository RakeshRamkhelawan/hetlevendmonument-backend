"""Auth router -- ADR-033 Laag 1 composiet (sub-routers bevatten de endpoints)."""

from fastapi import APIRouter

from .auth_config import auth_limiter as auth_limiter  # noqa: F401
from .dependencies import validate_csrf_token as validate_csrf_token  # noqa: F401
from .router_login import (  # noqa: F401
    _get_user_scopes,
    get_or_create_lockout_record,
    increment_failed_attempts,
    is_account_locked,
    reset_failed_attempts,
)
from .router_password import forgot_password as forgot_password  # noqa: F401
from .router_registration import register_user as register_user  # noqa: F401

from . import router_csrf, router_login, router_password, router_registration, router_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

router.include_router(router_registration.router)
router.include_router(router_login.router)
router.include_router(router_password.router)
router.include_router(router_csrf.router)
router.include_router(router_token.router)
