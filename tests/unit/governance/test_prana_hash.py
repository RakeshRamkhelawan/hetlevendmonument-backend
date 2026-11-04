"""Fase 1 -- prana transaction hash-chain digest (ADR-019).

Gate-2 M3: compute_audit_hash is shaped for tool-audit (agent_id/tool_name/status). A
prana-specific digest must bind the security-relevant prana fields (amount, department,
balance_after, kind) so tampering with a stored amount is detectable.
"""

import pytest

from src.core.governance.prana_hash import compute_prana_hash

_BASE = dict(
    tenant_id=7,
    department="finance",
    action_type="create_task",
    cost=50,
    kind="spend",
    actor_user_id=5,
    balance_after=9950,
    created_at="2026-07-15T10:00:00+00:00",
    previous_hash=None,
)


@pytest.mark.unit
def test_hash_is_deterministic():
    assert compute_prana_hash(**_BASE) == compute_prana_hash(**_BASE)


@pytest.mark.unit
def test_hash_is_64_hex_chars():
    h = compute_prana_hash(**_BASE)
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


@pytest.mark.unit
def test_tampering_with_amount_changes_hash():
    """Binding the amount makes a silently-edited cost detectable."""
    tampered = {**_BASE, "cost": 10}
    assert compute_prana_hash(**tampered) != compute_prana_hash(**_BASE)


@pytest.mark.unit
def test_department_is_bound():
    other = {**_BASE, "department": "hr"}
    assert compute_prana_hash(**other) != compute_prana_hash(**_BASE)


@pytest.mark.unit
def test_chain_links_via_previous_hash():
    """previous_hash chains records; None is the genesis marker."""
    genesis = compute_prana_hash(**_BASE)
    linked = compute_prana_hash(**{**_BASE, "previous_hash": genesis})
    assert linked != genesis
