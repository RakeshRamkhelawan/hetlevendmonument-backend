"""Governance domain dependencies -- decorators and helpers (ADR-033)."""

from collections.abc import Callable
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user
from src.core.governance.accuracy_monitor import AccuracyMonitor as AccuracyMonitor
from src.core.governance.alert_manager import GovernanceAlert as GovernanceAlert
from src.core.governance.authority_reporting import AuthorityReport as AuthorityReport
from src.core.governance.quality_management import QualityGate as QualityGate
from src.core.governance.rate_limiter import (
    governance_read_limit as _governance_read_limit,
    governance_write_limit as _governance_write_limit,
)
from src.core.governance.risk_register import RiskEntry as RiskEntry
from src.core.middleware.tenant_context import get_current_tenant_id


def governance_read_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrapper for governance read rate limiter."""
    return _governance_read_limit(func)


def governance_write_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrapper for governance write rate limiter."""
    return _governance_write_limit(func)
