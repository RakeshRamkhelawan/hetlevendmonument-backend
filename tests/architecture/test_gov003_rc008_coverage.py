"""Architecture test: legacy agent_endpoints.py moet council gate documenteren (RC-008).

TODO(SP-GOV-003): wire Agent Council gate in legacy agent_endpoints.py
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_legacy_agent_endpoints_has_council_gate() -> None:
    """RC-008: src/core/api/agent_endpoints.py MOET council gate bevatten of verwijzen.

    De v1/agents handlers hebben gates (SP-GOV-002 dag 1), maar de legacy flat-file
    agent_endpoints.py gaat direct naar execute zonder council review.
    """
    src = (_REPO_ROOT / "src/core/api/agent_endpoints.py").read_text(encoding="utf-8")
    assert "council" in src.lower(), (
        "RC-008: legacy agent_endpoints.py mist council gate -- "
        "voeg require_council_approval toe of documenteer expliciet als deprecated/out-of-scope"
    )
