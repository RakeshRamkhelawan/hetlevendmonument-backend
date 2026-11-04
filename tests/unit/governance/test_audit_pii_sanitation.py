"""SP-AUDIT-004: log_security_event mag geen rauwe details-dict loggen.

PII zoals email-adressen mogen niet in system logs verschijnen (ADR-019).
Rode test -- ROOD voor fix (huidige code logt details={details} direct als f-string).
"""

import logging

import pytest


@pytest.mark.asyncio
async def test_log_security_event_does_not_log_raw_details_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """log_security_event mag de rauwe waarden uit de details-dict niet loggen.

    Huidige code: f"... details={details}" -- logt volledige dict inclusief PII.
    Na fix: alleen sleutels loggen (f"details_keys={list(details.keys())}").
    SP-AUDIT-004 rode test -- ROOD voor fix-commit.
    """
    from src.core.governance.services.audit_service import log_security_event

    sensitive_details = {
        "email": "victim@example.com",
        "raw_token": "secret-bearer-xyz",
    }

    with caplog.at_level(logging.DEBUG):
        await log_security_event(
            event_type="CROSS_TENANT_ATTEMPT",
            tenant_id=1,
            details=sensitive_details,
        )

    for record in caplog.records:
        msg = record.getMessage()
        assert "victim@example.com" not in msg, (
            "log_security_event logt PII-waarde 'email' in system log -- ADR-019 schending"
        )
        assert "secret-bearer-xyz" not in msg, (
            "log_security_event logt gevoelige waarde 'raw_token' in system log -- ADR-019 schending"
        )


@pytest.mark.asyncio
async def test_log_security_event_logs_details_keys_not_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Na fix moet log_security_event de sleutels (niet waarden) vermelden.

    SP-AUDIT-004 -- gedragstest voor de gewenste situatie na fix.
    """
    from src.core.governance.services.audit_service import log_security_event

    details = {"user_agent": "curl/7.x", "attempt_count": "5"}

    with caplog.at_level(logging.DEBUG):
        await log_security_event(
            event_type="QUOTA_EXCEEDED",
            tenant_id=1,
            details=details,
        )

    key_logged = any(
        "user_agent" in record.getMessage() or "attempt_count" in record.getMessage()
        for record in caplog.records
    )
    value_logged = any(
        "curl/7.x" in record.getMessage() or record.getMessage().endswith("5")
        for record in caplog.records
    )
    assert key_logged, "Na fix moet log_security_event de sleutelnamen vermelden"
    assert not value_logged, "Na fix mag log_security_event de waarden NIET vermelden"
