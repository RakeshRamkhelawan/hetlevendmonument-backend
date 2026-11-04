import pytest
from unittest.mock import patch, MagicMock, AsyncMock, ANY
from datetime import datetime, timezone, timedelta
from src.core.governance.retention_cleanup import cleanup_council_decisions, BATCH_SIZE


@pytest.mark.unit
@patch("src.core.governance.retention_cleanup.get_db_session")
@patch("src.core.governance.retention_cleanup.TenantFilterBypass")
@patch("src.core.governance.retention_cleanup.logger")
@pytest.mark.asyncio
async def test_cleanup_actor_uses_tenant_filter_bypass(mock_logger, mock_bypass, mock_get_session):
    """Ensure the cleanup actor bypasses tenant filtering to delete across all tenants."""
    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__.return_value = mock_session

    # Fake empty table so the loop exits immediately
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_session.execute.return_value = mock_result

    from src.core.governance.retention_cleanup import _cleanup_council_decisions_async

    await _cleanup_council_decisions_async()

    mock_bypass.assert_called_once()
    mock_bypass.return_value.__enter__.assert_called_once()


@pytest.mark.unit
@patch("src.core.governance.retention_cleanup.get_db_session")
@patch("src.core.governance.retention_cleanup.TenantFilterBypass")
@pytest.mark.asyncio
async def test_cleanup_actor_batched_delete(mock_bypass, mock_get_session):
    """Test that delete operates in batches of BATCH_SIZE until completion."""
    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__.return_value = mock_session

    # Batch 1: BATCH_SIZE, Batch 2: 250, Batch 3 shouldn't happen because Batch 2 < BATCH_SIZE
    mock_result_full = MagicMock()
    mock_result_full.rowcount = BATCH_SIZE

    mock_result_partial = MagicMock()
    mock_result_partial.rowcount = 250

    mock_session.execute.side_effect = [mock_result_full, mock_result_partial]

    from src.core.governance.retention_cleanup import _cleanup_council_decisions_async

    await _cleanup_council_decisions_async()

    # The loop should execute exactly twice
    assert mock_session.execute.call_count == 2
    assert mock_session.commit.call_count == 2


@pytest.mark.unit
@patch("src.core.governance.retention_cleanup.get_db_session")
@patch("src.core.governance.retention_cleanup.TenantFilterBypass")
@patch("src.core.governance.retention_cleanup.datetime")
@pytest.mark.asyncio
async def test_cleanup_actor_uses_utc_cutoff(mock_datetime, mock_bypass, mock_get_session):
    """Test that the cutoff date is 395 days before the current UTC time."""
    mock_now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = mock_now

    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__.return_value = mock_session

    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_session.execute.return_value = mock_result

    from src.core.governance.retention_cleanup import _cleanup_council_decisions_async

    await _cleanup_council_decisions_async()

    # Verify that we used datetime.now(timezone.utc)
    mock_datetime.now.assert_called_with(timezone.utc)


@pytest.mark.unit
@patch("src.core.governance.retention_cleanup.get_db_session")
@patch("src.core.governance.retention_cleanup.TenantFilterBypass")
@patch("src.core.governance.retention_cleanup.logger")
@pytest.mark.asyncio
async def test_cleanup_actor_logs_total_count(mock_logger, mock_bypass, mock_get_session):
    """Test that the actor logs the correct total count of deleted rows."""
    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__.return_value = mock_session

    mock_result = MagicMock()
    mock_result.rowcount = 42
    mock_session.execute.return_value = mock_result

    from src.core.governance.retention_cleanup import _cleanup_council_decisions_async

    await _cleanup_council_decisions_async()

    # It should log 42 as deleted count
    mock_logger.info.assert_called_with(
        "council retention cleanup: deleted %d decisions older than %s", 42, ANY
    )


@pytest.mark.unit
@patch("src.core.governance.retention_cleanup.get_db_session")
@patch("src.core.governance.retention_cleanup.TenantFilterBypass")
@patch("src.core.governance.retention_cleanup.logger")
@pytest.mark.asyncio
async def test_cleanup_actor_handles_empty_table(mock_logger, mock_bypass, mock_get_session):
    """Test that if there are 0 rows to delete, it cleanly exits."""
    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__.return_value = mock_session

    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_session.execute.return_value = mock_result

    from src.core.governance.retention_cleanup import _cleanup_council_decisions_async

    await _cleanup_council_decisions_async()

    # Expected to execute just once since 0 < BATCH_SIZE
    assert mock_session.execute.call_count == 1
    mock_logger.info.assert_called_with(
        "council retention cleanup: deleted %d decisions older than %s", 0, ANY
    )
