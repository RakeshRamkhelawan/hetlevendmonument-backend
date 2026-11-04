"""SP-WE-24: router_registry forward-reference regression guard.

_register_notifications_v1 was a forward-reference stub that caused a sprint-blocker.
It was resolved by SP-API-001/002. This test prevents re-introduction.
"""

from pathlib import Path


def test_no_register_notifications_v1_forward_ref_in_registry() -> None:
    source = Path("src/core/api/router_registry.py").read_text(encoding="utf-8")
    assert "_register_notifications_v1" not in source, (
        "SP-WE-24: _register_notifications_v1 forward-reference mag niet terugkeren "
        "in router_registry.py. Gebruik de volledige router-registratie via "
        "register_all_routers() (SP-API-001/002 patroon)."
    )
