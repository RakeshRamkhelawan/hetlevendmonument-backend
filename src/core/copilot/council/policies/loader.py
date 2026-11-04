"""
Policy loader for the Agent Council.

Loads and merges per-tenant council policies with the system default.
Uses TTL caching to prevent excessive disk/DB lookups.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from cachetools import TTLCache

from src.core.copilot.council.policies.models import CouncilPolicy, OfficerPolicy

logger = logging.getLogger(__name__)

# Cache policies for 60 seconds.
_POLICY_CACHE: TTLCache[int, CouncilPolicy] = TTLCache[int, CouncilPolicy](maxsize=100, ttl=60)

DEFAULT_POLICY_PATH = Path(__file__).parent / "default.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Helper to load YAML from disk."""
    if not path.exists():
        logger.warning("Policy file not found: %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}


def _merge_dicts(
    base: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    override: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_policy(tenant_id: int) -> CouncilPolicy:
    """Load the effective policy for a tenant.

    1. Check cache.
    2. Start with system default.
    3. Apply tenant-specific overrides (placeholder for DB/File lookup).
    4. Validate with Pydantic.
    """
    cached = _POLICY_CACHE.get(tenant_id)
    if isinstance(cached, CouncilPolicy):
        return cached

    # 1. Load default
    default_raw = _load_yaml(DEFAULT_POLICY_PATH)

    # 2. Load tenant overrides (Placeholder)
    # In a real enterprise setup, this might come from a 'tenants' table
    # 'config' JSONB column or a per-tenant YAML file.
    tenant_overrides: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    # Simulated override for testing (to be expanded in tests)
    # if tenant_id == 999:
    #     tenant_overrides = {"officers": {"SecurityOfficer": {"can_veto": False}}}

    effective_raw = _merge_dicts(default_raw, tenant_overrides)

    try:
        policy = CouncilPolicy.model_validate(effective_raw)
    except Exception as e:
        logger.error(
            "Policy validation failed for tenant %d: %s. Falling back to hard default.",
            tenant_id,
            e,
        )
        # Final fallback: empty model (uses Pydantic defaults)
        policy = CouncilPolicy()

    _POLICY_CACHE[tenant_id] = policy
    return policy


def get_default_policy() -> CouncilPolicy:
    """Get the system default policy."""
    return load_policy(0)
