"""SP-AUDIT-004: log_action() moet expliciete waarschuwing geven bij tenant_id=None.

ADR-019: audit entries zonder tenant context zijn ongeldig.
Rode test -- ROOD voor fix (huidige code schrijft entry naar DB met None tenant_id).
"""

import logging
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_log_action_does_not_write_to_db_when_tenant_id_is_none() -> None:
    """log_action() mag session.add() NIET aanroepen als tenant_id=None.

    Huidige code: schrijft AuditLog met tenant_id=None naar DB (schending NOT NULL).
    Na fix: vroeg return None met logger.warning.
    SP-AUDIT-004 rode test -- ROOD voor fix-commit.
    """
    from src.core.governance.audit import AuditService

    mock_session = MagicMock()
    result = await AuditService.log_action(
        tenant_id=None,  # type: ignore[arg-type]
        action="TEST_NONE_TENANT",
        resource="test:1",
        session=mock_session,
    )

    assert result is None, (
        "log_action() moet None retourneren als tenant_id=None -- "
        "schrijven naar DB met None tenant_id schendt ADR-005 NOT NULL"
    )
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_log_action_logs_warning_when_tenant_id_is_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """log_action() moet een waarschuwing loggen als tenant_id=None.

    SP-AUDIT-004 rode test -- ROOD voor fix-commit.
    """
    from src.core.governance.audit import AuditService

    mock_session = MagicMock()
    with caplog.at_level(logging.WARNING, logger="src.core.governance.audit"):
        await AuditService.log_action(
            tenant_id=None,  # type: ignore[arg-type]
            action="TEST_NONE_TENANT_WARN",
            resource="test:2",
            session=mock_session,
        )

    assert any("tenant_id" in msg.lower() or "none" in msg.lower() for msg in caplog.messages), (
        "log_action() moet een WARNING loggen als tenant_id=None -- "
        "silent skip is niet detecteerbaar in productie"
    )
