"""Architecture guard: the emergency prana-allocation path MUST be PRANA_MANAGE-gated.

Gate-2 (security, HIGH): PranaService.allocate_emergency grants internal currency -- an
ungated route reaching it is a privilege-escalation. In Fase 1 the method exists with an
in-service authorized_by guard but NO router exposes it. This test is intentionally RED
until Fase 4 wires an endpoint that calls allocate_emergency AND enforces the
PRANA_MANAGE scope. It turns GREEN when (and only when) such a gated endpoint exists, so
the scope enforcement can never be forgotten.

TODO(SP-PRANA-ECONOMY): Fase 4 -- add POST /api/v1/prana/allocate behind
require_scope(PRANA_MANAGE); this test goes GREEN then.
"""

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2] / "src" / "core" / "api"


def test_emergency_allocation_endpoint_is_prana_manage_gated():
    """RED until Fase 4: no router may reach allocate_emergency without PRANA_MANAGE, and
    an endpoint reaching it MUST carry the scope. Passes once a router references both
    allocate_emergency and the PRANA_MANAGE scope in the same file."""
    gated_endpoint_found = False
    unguarded_hits: list[str] = []

    for py in _API_ROOT.rglob("*.py"):
        try:
            src = py.read_text(encoding="utf-8")
        except Exception:
            continue
        if "allocate_emergency" not in src:
            continue
        has_scope = "PRANA_MANAGE" in src or "prana:manage" in src
        if has_scope:
            gated_endpoint_found = True
        else:
            unguarded_hits.append(str(py.relative_to(_API_ROOT)))

    assert not unguarded_hits, (
        "allocate_emergency is reached by a router WITHOUT a PRANA_MANAGE scope guard "
        f"(privilege escalation risk): {unguarded_hits}"
    )
    assert gated_endpoint_found, (
        "No PRANA_MANAGE-gated endpoint reaches allocate_emergency yet -- "
        "TODO(SP-PRANA-ECONOMY) Fase 4 must wire POST /api/v1/prana/allocate behind "
        "require_scope(PRANA_MANAGE). RED until then (by design)."
    )
