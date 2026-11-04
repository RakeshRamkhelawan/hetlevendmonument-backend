"""Prana transaction hash-chain digest (ADR-019).

A dedicated digest for prana transactions (Gate-2 M3): compute_audit_hash in the
tool-audit module binds tool-specific fields (agent_id/tool_name/status/output_hash) that
do not fit a prana transaction. This mirrors the same canonical-JSON + SHA-256 approach
but binds the security-relevant prana fields so tampering with a stored amount, department
or resulting balance is detectable. The chain is per (tenant_id, department); previous_hash
links records, with ``genesis`` as the first-link marker.
"""

from __future__ import annotations

import hashlib
import json


def compute_prana_hash(
    *,
    tenant_id: int,
    department: str,
    action_type: str,
    cost: int,
    kind: str,
    actor_user_id: int | None,
    balance_after: int,
    created_at: str,
    previous_hash: str | None,
) -> str:
    """Tamper-evident SHA-256 digest over a prana transaction's security-relevant fields."""
    payload = {
        "tenant_id": tenant_id,
        "department": department,
        "action_type": action_type,
        "cost": cost,
        "kind": kind,
        "actor_user_id": actor_user_id,
        "balance_after": balance_after,
        "created_at": created_at,
        "previous_hash": previous_hash or "genesis",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
