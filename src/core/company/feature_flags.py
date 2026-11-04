"""Company-layer feature flag helpers.

This module provides a lightweight Redis-backed rollout gate for the
company layer. It supports:
- global kill switch
- explicit tenant whitelist
- percentage-based gradual rollout
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Optional, Set

import redis

from src.core.shared.rollout import stable_bucket

REDIS_KILL_SWITCH_KEY = "company_layer:kill_switch"
REDIS_WHITELIST_KEY = "company_layer:whitelist"
REDIS_ROLLOUT_KEY = "company_layer:rollout_percentage"


@dataclass
class _LocalConfig:
    kill_switch: bool = False
    rollout_percentage: int = 100
    whitelist: set[int] = field(default_factory=set)


_local_config = _LocalConfig(
    kill_switch=os.getenv("COMPANY_LAYER_KILL_SWITCH", "false").lower() == "true",
    rollout_percentage=int(os.getenv("COMPANY_LAYER_ROLLOUT_PERCENTAGE", "100")),
    whitelist={
        int(value)
        for value in os.getenv("COMPANY_LAYER_WHITELIST", "").split(",")
        if value.strip().isdigit()
    },
)


def _get_redis_client() -> Any | None:  # TODO(TYPE): replace Any with concrete type
    """Return Redis client if configured, otherwise None."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        client: Any = redis.Redis.from_url(  # TODO(TYPE): replace Any with concrete type
            redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        return client
    except Exception:
        return None


def _stable_bucket(tenant_id: int) -> int:
    """Map tenant_id to a stable 0-99 bucket for percentage rollout.

    De formule zelf staat sinds ADR-036 OP-02 in `src.core.shared.rollout`, zodat de
    skill-manifest-uitrol dezelfde verdeling gebruikt in plaats van een tweede kopie. Met de
    lege salt is de uitkomst byte-identiek aan de oorspronkelijke implementatie hier
    (`md5(str(tenant_id))`, eerste 8 hex-tekens, modulo 100): geen enkele tenant wisselt van
    bucket door deze verplaatsing. Vastgelegd in `tests/unit/shared/test_rollout_bucketing.py`.
    """
    return stable_bucket(tenant_id)


def _read_remote_config() -> _LocalConfig | None:
    client = _get_redis_client()
    if client is None:
        return None

    try:
        raw_kill = client.get(REDIS_KILL_SWITCH_KEY)
        raw_rollout = client.get(REDIS_ROLLOUT_KEY)
        raw_whitelist = client.get(REDIS_WHITELIST_KEY)

        kill_switch = (
            str(raw_kill).lower() == "true" if raw_kill is not None else _local_config.kill_switch
        )
        rollout = int(raw_rollout) if raw_rollout is not None else _local_config.rollout_percentage

        whitelist: set[int] = set(_local_config.whitelist)
        if raw_whitelist:
            parsed = json.loads(raw_whitelist)
            whitelist = {int(value) for value in parsed}

        return _LocalConfig(
            kill_switch=kill_switch,
            rollout_percentage=max(0, min(100, rollout)),
            whitelist=whitelist,
        )
    except Exception:
        return None


def _active_config() -> _LocalConfig:
    remote = _read_remote_config()
    if remote is not None:
        return remote

    _local_config.rollout_percentage = max(0, min(100, _local_config.rollout_percentage))
    return _local_config


def is_company_layer_enabled(tenant_id: int) -> bool:
    """Return True when company layer is enabled for the provided tenant."""
    config = _active_config()

    if config.kill_switch:
        return False

    if tenant_id in config.whitelist:
        return True

    if config.rollout_percentage >= 100:
        return True

    if config.rollout_percentage <= 0:
        return False

    return _stable_bucket(tenant_id) < config.rollout_percentage


def set_company_layer_kill_switch(enabled: bool) -> None:
    """Set kill switch locally (and in Redis when available)."""
    _local_config.kill_switch = bool(enabled)
    client = _get_redis_client()
    if client is not None:
        client.set(REDIS_KILL_SWITCH_KEY, "true" if enabled else "false")


def set_company_layer_rollout_percentage(percentage: int) -> None:
    """Set rollout percentage locally (and in Redis when available)."""
    bounded = max(0, min(100, int(percentage)))
    _local_config.rollout_percentage = bounded
    client = _get_redis_client()
    if client is not None:
        client.set(REDIS_ROLLOUT_KEY, bounded)


def set_company_layer_whitelist(tenant_ids: Iterable[int]) -> None:
    """Set tenant whitelist locally (and in Redis when available)."""
    whitelist = {int(value) for value in tenant_ids}
    _local_config.whitelist = whitelist

    client = _get_redis_client()
    if client is not None:
        client.set(REDIS_WHITELIST_KEY, json.dumps(sorted(whitelist)))
