"""Audit logging utilities for tool execution."""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


def compute_output_hash(output: Any) -> str:  # TODO(TYPE): replace Any with concrete type
    """Compute SHA-256 hash of tool output for tamper detection."""
    try:
        canonical = json.dumps(output, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
    except (TypeError, ValueError):
        return hashlib.sha256(str(output).encode()).hexdigest()


def compute_audit_hash(
    tenant_id: int,
    agent_id: str,
    tool_name: str,
    timestamp: datetime,
    status: str,
    output_hash: str | None,
    previous_hash: str | None,
    tool_input: Any = None,  # TODO(TYPE): replace Any with concrete type
    task_id: str | None = None,
    error_detail: str | None = None,
    hitl_ticket_ref: str | None = None,
    hitl_approved_by: str | None = None,
) -> str:
    """Compute SHA-256 hash of audit record for chain integrity.

    OP-28: `tool_input`/`task_id`/`error_detail`/`hitl_ticket_ref`/`hitl_approved_by` are
    caller-supplied `ToolAuditLog` columns that used to fall outside this hash -- changeable
    without breaking chain verification. There is exactly one call site (`audit_repository.py`,
    the write path) and no independent recompute-and-compare verifier for this chain anywhere
    in the codebase, so widening the payload here does not invalidate any previously persisted
    `audit_hash` (nothing re-derives and compares those).
    """
    data = {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "timestamp": timestamp.isoformat(),
        "status": status,
        "output_hash": output_hash,
        "previous_hash": previous_hash or "genesis",
        "tool_input": tool_input,
        "task_id": task_id,
        "error_detail": error_detail,
        "hitl_ticket_ref": hitl_ticket_ref,
        "hitl_approved_by": hitl_approved_by,
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def sanitize_tool_output(output: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Sanitize tool output for audit storage (remove PII).

    LET OP -- dit is een BLOCKLIST op sleutelnamen en dus per definitie onvolledig voor
    modeloutput. Een payload of resultaat dat door een taalmodel is geschreven kan elke
    sleutelnaam hebben: `{"employee_id": "jan.jansen@acme.nl"}` bevat geen enkele verboden
    naam en glipt er ongehinderd door. Dat was letterlijk de bevinding van de Gate 2-review
    van BE-AGT-044.

    Voor de INVOER is dit daarom vervangen door een allowlist met keyed digests
    (`tool_broker/redaction.py`, ADR-036 OP-27). Deze functie blijft als tweede laag op de
    UITVOER staan, waar de vorm door de tool zelf wordt bepaald en een blocklist dus wel
    zinvol is. Vertrouw er niet op voor door een model geschreven inhoud.
    """
    if not isinstance(output, dict):
        return output

    pii_keys = {"password", "secret", "token", "api_key", "ssn", "email", "phone"}
    sanitized = {}

    for key, value in output.items():
        if any(pii in str(key).lower() for pii in pii_keys):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_tool_output(value)
        else:
            sanitized[key] = value

    return sanitized
