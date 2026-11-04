"""
Worker tenant-context utilities for single-tenant deployments (AUDIT-ST-03, ADR-035).

In single-tenant mode, Dramatiq workers may run without a JWT-injected tenant_id.
This module provides a context manager that sets tenant_id=1 when needed, and
cleans up on exit to prevent bleed between pooled worker threads.
"""

import functools
import os
from contextlib import contextmanager
from typing import Generator

from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id


def resolve_single_tenant_fallback_id() -> int | None:
    """Return 1 in single-tenant deployments (ADR-035), else None.

    Standalone from the ContextVar so callers without an active request/worker
    context (e.g. CVAAutonomousTrigger, ADR-036 OP-12) can resolve the fallback
    tenant explicitly instead of reading a ContextVar that is None outside a
    request scope.
    """
    if os.getenv("DEPLOYMENT_MODE", "saas").lower() == "single_tenant":
        return 1
    return None


@contextmanager
def single_tenant_worker_context() -> Generator[None, None, None]:
    injected = False
    if get_tenant_id() is None:
        fallback_id = resolve_single_tenant_fallback_id()
        if fallback_id is not None:
            set_tenant_id(fallback_id)
            injected = True
    try:
        yield
    finally:
        if injected:
            set_tenant_id(None)


def ensure_single_tenant_context(func):  # type: ignore[no-untyped-def]
    @functools.wraps(func)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        with single_tenant_worker_context():
            return func(*args, **kwargs)

    return wrapper
