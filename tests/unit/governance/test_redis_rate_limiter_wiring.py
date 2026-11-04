"""SEC-001/005: CVA rate limiters moeten een Redis-backed backend hebben.

Verifieert dat governance/rate_limiter.py RedisRateLimiter gebruikt met InMemory fallback.
Governance is de juiste laag voor Redis-initialisatie (DSM: shared mag geen database/security
imports hebben per fan-out=0 invariant; governance mag wel importeren uit die lagen).
"""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_governance_rate_limiter_uses_redis_backend() -> None:
    """governance/rate_limiter.py moet RedisRateLimiter gebruiken voor cva_chat_limit.

    SEC-001/005: InMemoryRateLimiter is per-process. Met N Gunicorn workers is de effectieve
    limiet N*30 req/min. Redis-backend is cross-worker atomisch.
    Fix: governance initialiseert RedisRateLimiter en gebruikt die in cva_chat_limit.
    """
    source = (_REPO_ROOT / "src/core/governance/rate_limiter.py").read_text(encoding="utf-8")
    assert "RedisRateLimiter" in source, (
        "governance/rate_limiter.py gebruikt geen RedisRateLimiter. "
        "SEC-001/005: cva_chat_limit moet Redis-backed zijn om multi-worker bypass te voorkomen."
    )


@pytest.mark.unit
def test_governance_rate_limiter_has_redis_fallback() -> None:
    """governance/rate_limiter.py moet InMemory fallback hebben als Redis niet beschikbaar is.

    SEC-001/005: dev/test-omgevingen draaien zonder Redis. Fallback naar InMemoryRateLimiter
    zorgt dat deze omgevingen blijven werken.
    """
    source = (_REPO_ROOT / "src/core/governance/rate_limiter.py").read_text(encoding="utf-8")
    has_redis = "RedisRateLimiter" in source
    has_inm_fallback = "_rate_limiter.is_allowed" in source
    assert has_redis, (
        "governance/rate_limiter.py heeft geen RedisRateLimiter. "
        "SEC-001/005: Redis-backend vereist voor cross-worker rate limiting."
    )
    assert has_inm_fallback, (
        "governance/rate_limiter.py heeft geen InMemory fallback (_rate_limiter.is_allowed). "
        "SEC-001/005: Redis-failure moet graceful degraderen naar InMemory."
    )


@pytest.mark.unit
def test_cva_chat_limit_inherits_redis_backend() -> None:
    """cva_chat_limit moet in governance/rate_limiter.py staan en RedisRateLimiter gebruiken.

    SEC-005: cva_chat_limit is de decorator die alle CVA chat endpoints beschermt.
    Moet de Redis-backed governance-implementatie gebruiken.
    """
    source = (_REPO_ROOT / "src/core/governance/rate_limiter.py").read_text(encoding="utf-8")
    assert "cva_chat_limit" in source, (
        "governance/rate_limiter.py bevat geen cva_chat_limit. "
        "SEC-005: CVA rate limit decorator moet in governance staan."
    )
    assert "RedisRateLimiter" in source, (
        "governance/rate_limiter.py bevat cva_chat_limit maar geen RedisRateLimiter. "
        "SEC-005: cva_chat_limit moet Redis-backed zijn."
    )
