"""Unit tests for Task 3.2 memory domain sync wiring.

Covers:
  - _sync_observations_to_memory: MemoryWriteService called for consented users
  - _sync_observations_to_memory: skipped when cross_session_memory=False
  - get_profile: memory_snapshot included when ContextPackerService returns content
  - get_profile: memory_snapshot absent when estimated_tokens == 0
"""

from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.learning.batching.batch_manager import (
    PendingObservation,
    _sync_observations_to_memory,
)
from src.core.learning.consent.consent_manager import ConsentCategories


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _obs(
    user_id: str = "abcdef1234567890",
    tenant_id: int = 1,
    behavior_type: str = "file_edit",
    session_id: str = "sess-001",
) -> PendingObservation:
    return PendingObservation(
        human_user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        behavior_type=behavior_type,
        context={"file": "main.py", "edit_count": 3},
        confidence_score=0.9,
    )


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# _sync_observations_to_memory tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestSyncObservationsToMemory:
    @patch("src.core.learning.batching.batch_manager.MemoryWriteService")
    @patch("src.core.learning.batching.batch_manager.TwinConsentManager")
    async def test_memory_write_called_for_consented_user(
        self, MockConsent: MagicMock, MockMemory: MagicMock
    ) -> None:
        """When both behavior_tracking and cross_session_memory are True,
        MemoryWriteService.write() is called for each observation."""
        session = _make_session()
        mock_sf = MagicMock(return_value=session)

        MockConsent.return_value.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                cross_session_memory=True,
            )
        )
        mock_svc = AsyncMock()
        MockMemory.return_value = mock_svc

        batch = [_obs(), _obs(behavior_type="cursor_move")]

        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = mock_sf
            with patch("src.core.learning.batching.batch_manager.MemoryItemWrite"):
                await _sync_observations_to_memory(batch)

        assert mock_svc.write.await_count == 2
        session.commit.assert_awaited_once()

    @patch("src.core.learning.batching.batch_manager.TwinConsentManager")
    async def test_memory_write_skipped_when_cross_session_memory_false(
        self, MockConsent: MagicMock
    ) -> None:
        """When cross_session_memory=False, no write occurs."""
        session = _make_session()
        mock_sf = MagicMock(return_value=session)

        MockConsent.return_value.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=True,
                cross_session_memory=False,  # <-- revoked
            )
        )

        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = mock_sf
            with patch("src.core.learning.batching.batch_manager.MemoryWriteService") as MockMemory:
                await _sync_observations_to_memory([_obs()])

        MockMemory.assert_not_called()
        session.commit.assert_not_awaited()

    @patch("src.core.learning.batching.batch_manager.TwinConsentManager")
    async def test_memory_write_skipped_when_behavior_tracking_false(
        self, MockConsent: MagicMock
    ) -> None:
        """When behavior_tracking=False, no write occurs even if cross_session_memory=True."""
        session = _make_session()
        mock_sf = MagicMock(return_value=session)

        MockConsent.return_value.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(
                behavior_tracking=False,
                cross_session_memory=True,
            )
        )

        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = mock_sf
            with patch("src.core.learning.batching.batch_manager.MemoryWriteService") as MockMemory:
                await _sync_observations_to_memory([_obs()])

        MockMemory.assert_not_called()

    async def test_skipped_when_session_maker_is_none(self) -> None:
        """When db_manager.async_session_maker is None, function returns without crash."""
        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = None
            # Should not raise
            await _sync_observations_to_memory([_obs()])

    @patch("src.core.learning.batching.batch_manager.TwinConsentManager")
    async def test_one_session_per_user_group(self, MockConsent: MagicMock) -> None:
        """Two observations from the same user open only one DB session."""
        session = _make_session()
        mock_sf = MagicMock(return_value=session)

        MockConsent.return_value.get_consent_categories = AsyncMock(
            return_value=ConsentCategories(behavior_tracking=True, cross_session_memory=True)
        )

        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = mock_sf
            with patch("src.core.learning.batching.batch_manager.MemoryWriteService"):
                with patch("src.core.learning.batching.batch_manager.MemoryItemWrite"):
                    await _sync_observations_to_memory(
                        [
                            _obs(user_id="user1", session_id="s1"),
                            _obs(user_id="user1", session_id="s2"),
                        ]
                    )

        # Only one session opened for one unique (user_id, tenant_id) group
        assert mock_sf.call_count == 1


# ---------------------------------------------------------------------------
# get_profile memory snapshot tests
# ---------------------------------------------------------------------------


def _make_twin_service() -> Any:
    from src.core.learning.services.practical_twin_service import PracticalTwinService

    # observer is required; use a MagicMock to avoid wiring the full pipeline
    observer = MagicMock()
    # consent_manager=None so the consent gate is skipped in get_profile
    return PracticalTwinService(observer=observer, consent_manager=None)


def _make_db(profile_obj: MagicMock | None) -> AsyncMock:
    db = AsyncMock()
    cursor = AsyncMock()
    cursor.scalar_one_or_none = MagicMock(return_value=profile_obj)
    db.execute = AsyncMock(return_value=cursor)
    return db


def _make_profile() -> MagicMock:
    p = MagicMock()
    p.coding_style = {"indent": "spaces"}
    p.work_patterns = {}
    p.optimal_help_style = "detailed"
    p.confidence_level = 0.75
    p.observation_count = 10
    return p


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetProfileMemorySnapshot:
    @patch.dict("os.environ", {"TWIN_MEMORY_SYNC_ENABLED": "true"})
    async def test_profile_includes_memory_snapshot(self) -> None:
        """When TWIN_MEMORY_SYNC_ENABLED=true and ContextPackerService returns items,
        the profile dict includes memory_snapshot."""
        from src.core.learning.services.practical_twin_service import PracticalTwinService

        svc = _make_twin_service()
        profile = _make_profile()
        db = _make_db(profile)

        mock_ep = MagicMock()
        mock_ep.content = "User edited main.py"
        mock_ep.memory_type = "episodic"

        mock_snapshot = {
            "recent_episodes": [mock_ep],
            "top_facts": [],
            "estimated_tokens": 42,
        }

        with patch(
            "src.domains.memory.services.context_packer_service.ContextPackerService"
        ) as MockPacker:
            MockPacker.return_value.build = AsyncMock(return_value=mock_snapshot)
            result = await svc.get_profile("u1", 1, db)

        assert isinstance(svc, PracticalTwinService)
        assert "memory_snapshot" in result
        assert result["memory_snapshot"]["estimated_tokens"] == 42
        assert len(result["memory_snapshot"]["recent_episodes"]) == 1

    @patch.dict("os.environ", {"TWIN_MEMORY_SYNC_ENABLED": "true"})
    async def test_memory_snapshot_absent_when_no_content(self) -> None:
        """When ContextPackerService returns estimated_tokens=0, memory_snapshot
        is NOT added to the profile (avoids empty noise)."""
        svc = _make_twin_service()
        db = _make_db(_make_profile())

        empty_snapshot = {"recent_episodes": [], "top_facts": [], "estimated_tokens": 0}

        with patch(
            "src.domains.memory.services.context_packer_service.ContextPackerService"
        ) as MockPacker:
            MockPacker.return_value.build = AsyncMock(return_value=empty_snapshot)
            result = await svc.get_profile("u1", 1, db)

        assert "memory_snapshot" not in result
        assert result["coding_style"] == {"indent": "spaces"}

    @patch.dict("os.environ", {"TWIN_MEMORY_SYNC_ENABLED": "false"})
    async def test_memory_snapshot_absent_when_flag_off(self) -> None:
        """When TWIN_MEMORY_SYNC_ENABLED=false, ContextPackerService is never called."""
        svc = _make_twin_service()
        db = _make_db(_make_profile())

        with patch(
            "src.domains.memory.services.context_packer_service.ContextPackerService"
        ) as MockPacker:
            result = await svc.get_profile("u1", 1, db)

        MockPacker.assert_not_called()
        assert "memory_snapshot" not in result
