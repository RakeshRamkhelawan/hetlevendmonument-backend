"""Architecture tests for pre-existing rate-limiter security backlog items.

SEC-001: _get_user_id_from_request trusts raw X-User-ID header without JWT verification.
         A caller can spoof any user_id by setting that header.
SEC-002: Default privacy_rate_limit key is "{user_id}:{endpoint}" -- no tenant_id.
         User from tenant A with same numeric id as tenant B exhausts tenant B's quota.

Both are pre-existing issues outside SP-CVA-P1 dag 2 scope.
These tests are INTENTIONALLY RED until the backlog items are fixed.

TODO(SP-SEC-RL-001): fix SEC-001 -- remove raw X-User-ID header fallback from
    _get_user_id_from_request(); derive user identity exclusively from JWT / request.state.user.
TODO(SP-SEC-RL-002): fix SEC-002 -- include tenant_id in default privacy_rate_limit key;
    update _get_user_id_from_request or pass tenant_id into key_func.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_RL = _REPO_ROOT / "src/core/shared/rate_limiter.py"


@pytest.mark.unit
def test_sec001_rate_limiter_does_not_trust_raw_x_user_id_header() -> None:
    """TODO(SP-SEC-RL-001): _get_user_id_from_request must not fall back to X-User-ID header.

    Currently the function checks request.headers["X-User-ID"] without verifying
    authenticity. Any unauthenticated caller can set this header to any value and
    bypass per-user rate limiting.

    Fix: remove the header branch; rely exclusively on request.state.user (JWT-derived).
    """
    source = _SHARED_RL.read_text(encoding="utf-8")
    assert "X-User-ID" not in source, (
        "SEC-001 (BACKLOG): _get_user_id_from_request still accepts raw X-User-ID header. "
        "This allows header spoofing to bypass per-user rate limits. "
        "Fix in TODO(SP-SEC-RL-001): derive user id solely from JWT / request.state.user."
    )


@pytest.mark.unit
def test_sec002_default_rate_limit_key_includes_tenant_id() -> None:
    """TODO(SP-SEC-RL-002): default privacy_rate_limit key must include tenant_id.

    Current default key is "{user_id}:{endpoint}" -- no tenant_id.
    Two tenants whose integer user_ids collide share a rate-limit bucket, allowing
    a user in tenant A to exhaust quota for a user in tenant B.

    Fix in TODO(SP-SEC-RL-002): include tenant_id in _get_user_id_from_request or
    adjust the default key_func in privacy_rate_limit to prepend tenant_id.
    """
    source = _SHARED_RL.read_text(encoding="utf-8")
    # The default key_func must produce a key that contains tenant_id.
    # After the fix, _get_user_id_from_request should return "{tenant_id}:{user_id}"
    # OR the default key in privacy_rate_limit should be f"{tenant_id}:{user_id}:{endpoint}".
    # We check for the minimal invariant: tenant_id must appear in the default key construction.
    default_key_line = 'key = f"{user_id}:{endpoint}"'
    assert default_key_line not in source, (
        "SEC-002 (BACKLOG): default privacy_rate_limit key is '{user_id}:{endpoint}' -- "
        "tenant_id is absent. Cross-tenant rate-limit collision possible. "
        "Fix in TODO(SP-SEC-RL-002): include tenant_id in the key."
    )
