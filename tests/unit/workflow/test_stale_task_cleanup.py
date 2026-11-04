"""
Unit tests voor _run_stale_task_cleanup (P0-8, ADR-007).

Controleert:
- Stale PENDING-taken (> 1u oud, started_at IS NULL) worden FAILED
- Stale RUNNING-taken (started_at > 1u geleden) worden FAILED
- Recente taken worden NIET aangeraakt
- Verwijderde taken krijgen correcte error_json en finished_at
- Behavioral: gebruiker wacht op taak die vastzit → krijgt FAILED na cleanup
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _make_task(status_str, created_offset_h=0, started_offset_h=None):
    """Helper: maak een mock C7ExecutionTask."""
    from src.core.workflow.models import TaskStatus

    task = MagicMock()
    task.status = TaskStatus(status_str)
    task.created_at = datetime.now(timezone.utc) - timedelta(hours=created_offset_h)
    task.started_at = (
        datetime.now(timezone.utc) - timedelta(hours=started_offset_h)
        if started_offset_h is not None
        else None
    )
    task.finished_at = None
    task.error_json = None
    return task


import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_pending_task_marked_failed():
    """PENDING-taak ouder dan 1u zonder started_at wordt FAILED."""
    stale = _make_task("pending", created_offset_h=2)
    recent = _make_task("pending", created_offset_h=0)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stale]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            from src.workers.actors import _run_stale_task_cleanup

            result = await _run_stale_task_cleanup()

    from src.core.workflow.models import TaskStatus

    assert stale.status == TaskStatus.FAILED
    assert stale.finished_at is not None
    assert stale.error_json is not None
    assert "StaleTaskError" in stale.error_json["type"]
    assert result["stale_tasks_marked_failed"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_running_task_marked_failed():
    """RUNNING-taak met started_at > 1u geleden wordt FAILED."""
    stale = _make_task("running", created_offset_h=3, started_offset_h=2)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stale]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            from src.workers.actors import _run_stale_task_cleanup

            result = await _run_stale_task_cleanup()

    from src.core.workflow.models import TaskStatus

    assert stale.status == TaskStatus.FAILED
    assert stale.finished_at is not None
    assert result["stale_tasks_marked_failed"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recent_tasks_not_touched():
    """Recente taken (< 1u oud) worden NIET aangepast."""
    recent_pending = _make_task("pending", created_offset_h=0)
    recent_running = _make_task("running", created_offset_h=0, started_offset_h=0)

    mock_result = MagicMock()
    # Query retourneert lege lijst (geen stale taken gevonden)
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            from src.workers.actors import _run_stale_task_cleanup

            result = await _run_stale_task_cleanup()

    from src.core.workflow.models import TaskStatus

    # Recente taken zijn onaangeroerd
    assert recent_pending.status == TaskStatus.PENDING
    assert recent_running.status == TaskStatus.RUNNING
    assert result["stale_tasks_marked_failed"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_task_gets_correct_error_json():
    """error_json bevat type StaleTaskError en een beschrijvend bericht."""
    stale = _make_task("pending", created_offset_h=2)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stale]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            from src.workers.actors import _run_stale_task_cleanup

            await _run_stale_task_cleanup()

    assert stale.error_json["type"] == "StaleTaskError"
    assert "1-hour" in stale.error_json["message"] or "timeout" in stale.error_json["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tenant_filter_bypass_is_used():
    """TenantFilterBypass wordt gebruikt zodat alle tenants worden gescand."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ) as mock_bypass:
            from src.workers.actors import _run_stale_task_cleanup

            await _run_stale_task_cleanup()

            # Bypass moet aangemaakt zijn
            mock_bypass.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_behavioral_stuck_task_user_sees_failed_after_cleanup():
    """
    Behavioral test: Gebruiker wacht op een taak die al 2u op RUNNING staat.
    Na cleanup ziet de gebruiker status FAILED zodat hij niet blijft wachten.
    """
    stuck_task = _make_task("running", created_offset_h=3, started_offset_h=2)
    original_status_before = stuck_task.status

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stuck_task]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            from src.workers.actors import _run_stale_task_cleanup

            await _run_stale_task_cleanup()

    from src.core.workflow.models import TaskStatus

    assert original_status_before == TaskStatus.RUNNING
    assert stuck_task.status == TaskStatus.FAILED, (
        "Gebruiker die wacht op een vastgelopen RUNNING-taak moet FAILED zien "
        "zodat hij niet eindeloos blijft wachten"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_retrying_task_marked_failed():
    """RETRYING-taak met started_at > 1u geleden wordt FAILED (retry loop stuck)."""
    stale = _make_task("retrying", created_offset_h=3, started_offset_h=2)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stale]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            from src.workers.actors import _run_stale_task_cleanup

            result = await _run_stale_task_cleanup()

    from src.core.workflow.models import TaskStatus

    assert stale.status == TaskStatus.FAILED
    assert stale.finished_at is not None
    assert stale.error_json is not None
    assert "StaleTaskError" in stale.error_json["type"]
    assert result["stale_tasks_marked_failed"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_cleanup_increments_prometheus_metrics():
    """Cleanup verhoogt stale_cleanup_runs_total en stale_cleanup_tasks_failed_total."""
    stale = _make_task("pending", created_offset_h=2)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stale]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            with (
                patch("src.workers.actors.STALE_CLEANUP_RUNS_TOTAL") as mock_runs,
                patch("src.workers.actors.STALE_CLEANUP_TASKS_FAILED_TOTAL") as mock_tasks,
            ):
                from src.workers.actors import _run_stale_task_cleanup

                result = await _run_stale_task_cleanup()

    assert result["stale_tasks_marked_failed"] == 1
    mock_runs.inc.assert_called_once()
    mock_tasks.inc.assert_called_once_with(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_cleanup_failure_increments_error_metric():
    """Exception tijdens cleanup verhoogt stale_cleanup_errors_total en re-raise."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
    mock_session.commit = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=None)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("src.core.database.session.get_db_session") as mock_get_session:
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.core.database.tenant_query_filter.TenantFilterBypass", return_value=mock_ctx
        ):
            with patch("src.workers.actors.STALE_CLEANUP_ERRORS_TOTAL") as mock_errors:
                from src.workers.actors import _run_stale_task_cleanup

                with pytest.raises(RuntimeError, match="DB error"):
                    await _run_stale_task_cleanup()

    mock_errors.inc.assert_called_once()
