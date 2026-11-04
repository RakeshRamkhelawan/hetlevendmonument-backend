"""Prana economy runtime configuration.

The enforcement flag gates the copilot economy so it can be rolled out safely: with the
flag OFF (default) has_budget returns True and no charge happens -- so wiring the real
service does not change copilot behaviour before every tenant has provisioned budgets.
It is flipped ON in production (an explicit step) only after provisioning + backfill.
Same env-var convention as CVA_GOVERNANCE_FAIL_SECURE (src/core/services/cva_service.py).
"""

from __future__ import annotations

import os

# ADR-021: initial/refill prana per department per tenant.
PRANA_PER_DEPARTMENT = 10000

_TRUTHY = {"1", "true", "yes", "on"}


def prana_enforcement_enabled() -> bool:
    """Whether prana budget enforcement (has_budget gating + charging) is active."""
    return os.getenv("PRANA_ENFORCEMENT_ENABLED", "false").strip().lower() in _TRUTHY


def prana_grace_floor() -> int:
    """ADR-021 grace period: how far a department balance may temporarily go negative
    (available >= cost - grace). Default 0 = strict (auto-block at 0). A positive value is
    an explicit, bounded allowance; negative/invalid values clamp to 0."""
    raw = os.getenv("PRANA_GRACE_FLOOR", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0
