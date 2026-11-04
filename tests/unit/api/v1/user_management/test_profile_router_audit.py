"""SP-AUDIT-003 Dag 2: update_user_status audit log moet in best_effort staan.

Patroon conform test_audit_service_hash_chain.py (inspect.getsource).
"""

import inspect

from src.core.api.v1.user_management.profile_router import update_user_status


def test_update_user_status_audit_wrapped_in_best_effort():
    """ADR-019: het audit log in update_user_status moet in best_effort staan
    zodat een falende audit log het primaire request niet blokkeert.
    SP-AUDIT-003 Dag 2 -- red test BEFORE fix.
    """
    src = inspect.getsource(update_user_status)
    assert "best_effort" in src, (
        "update_user_status() roept log_action() aan zonder best_effort wrapper -- ADR-019 schending"
    )
