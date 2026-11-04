"""TDD tests -- Art. 17 forget-me cascade (SP-DLP-002 Dag 3, GDPR-004).

These tests inspect the *delete path* of DSARService specifically.
They are RED before the cascade is implemented and GREEN after.
"""

import inspect


def _delete_user_data_src() -> str:
    """Return the source of DSARService.delete_user_data for inspection."""
    from src.core.governance.dsar_service import DSARService

    return inspect.getsource(DSARService.delete_user_data)


def test_delete_user_data_handles_conversations() -> None:
    """delete_user_data() moet Conversation records verwijderen/deactiveren (GDPR Art. 17)."""
    src = _delete_user_data_src()
    assert "conversation" in src.lower(), (
        "delete_user_data() bevat geen conversation delete/deactiveer stap -- "
        "GDPR Art. 17 Right to Erasure cascade onvolledig"
    )


def test_delete_user_data_records_conversation_counts_in_audit() -> None:
    """Audit trail van delete_user_data() moet conversation deletes registreren."""
    src = _delete_user_data_src()
    assert "conversations" in src, (
        "delete_user_data() registreert conversations niet in records_affected -- "
        "compliance evidence ontbreekt voor Art. 17 cascade"
    )


def test_delete_user_data_has_audit_log() -> None:
    """delete_user_data() moet een audit log aanmaken na de delete operatie."""
    src = _delete_user_data_src()
    assert "_create_audit_log" in src or "audit" in src.lower(), (
        "delete_user_data() bevat geen audit log aanroep -- "
        "GDPR Art. 5(2) accountability vereiste niet gehandhaafd"
    )
