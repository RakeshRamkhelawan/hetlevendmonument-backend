"""
RC-009a: Agent execute/collaborate endpoints MOETEN een rate limit hebben.

Tests zijn ROOD totdat RC-009a fix is geimplementeerd (SP-GOV-002 dag 2).
Na de fix:
  - rate_limiter.py exporteert agent_execute_limit (10/min, tenant-keyed)
  - agent_execution_router.py gebruikt agent_execute_limit (via Depends)
  - agent_management_router.py gebruikt agent_execute_limit (via Depends)
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_execute_router_has_rate_limit() -> None:
    """RC-009a: agent_execution_router.py MOET agent_execute_limit gebruiken."""
    src = (_REPO_ROOT / "src/core/api/v1/agents/agent_execution_router.py").read_text(
        encoding="utf-8"
    )
    assert "agent_execute_limit" in src, (
        "RC-009a ONTBREEKT: agent_execution_router.py heeft geen agent_execute_limit -- "
        "execute endpoints zijn onbeschermd tegen DoS (SP-GOV-002 dag 2)"
    )


def test_management_router_has_rate_limit() -> None:
    """RC-009a: agent_management_router.py MOET agent_execute_limit gebruiken (collaborate)."""
    src = (_REPO_ROOT / "src/core/api/v1/agents/agent_management_router.py").read_text(
        encoding="utf-8"
    )
    assert "agent_execute_limit" in src, (
        "RC-009a ONTBREEKT: agent_management_router.py heeft geen agent_execute_limit -- "
        "collaborate endpoint is onbeschermd tegen DoS (SP-GOV-002 dag 2)"
    )


def test_rate_limiter_exports_agent_execute_limit() -> None:
    """RC-009a: rate_limiter.py MOET agent_execute_limit exporteren."""
    src = (_REPO_ROOT / "src/core/governance/rate_limiter.py").read_text(encoding="utf-8")
    assert "agent_execute_limit" in src, (
        "RC-009a ONTBREEKT: rate_limiter.py definieert geen agent_execute_limit -- "
        "voeg toe als Redis-backed rate limiter (10/min per tenant+user) (SP-GOV-002 dag 2)"
    )
