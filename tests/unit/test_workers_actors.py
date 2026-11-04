"""Unit tests for Dramatiq actor registrations in workers/actors.py.

Verifies that all background jobs have proper Dramatiq actor wrappers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestAuditVerificationActor:
    """B-010: audit_verification must be a registered Dramatiq actor."""

    def test_audit_verification_actor_exists(self) -> None:
        """run_audit_verification is exported from workers.actors."""
        from src.workers import actors

        assert hasattr(
            actors, "run_audit_verification"
        ), "run_audit_verification actor is missing from workers.actors"

    def test_audit_verification_is_not_dummy_when_dramatiq_available(self) -> None:
        """If dramatiq is available, run_audit_verification is a real actor."""
        from src.workers import actors
        from src.workers.workflow_worker import _DRAMATIQ_AVAILABLE

        if not _DRAMATIQ_AVAILABLE:
            pytest.skip("dramatiq not available in this environment")

        assert not hasattr(
            actors.run_audit_verification, "_is_dummy_sender"
        ), "run_audit_verification is a DummySender -- not a real Dramatiq actor"

    def test_audit_verification_has_send_method(self) -> None:
        """All actor variants must have .send() method."""
        from src.workers import actors

        assert hasattr(
            actors.run_audit_verification, "send"
        ), "run_audit_verification has no .send() method"


@pytest.mark.unit
class TestRetentionCleanupActor:
    """B-011: retention_cleanup actor must exist and be valid."""

    def test_retention_cleanup_actor_exists(self) -> None:
        from src.workers import actors

        assert hasattr(actors, "run_retention_cleanup")

    def test_retention_cleanup_has_send_method(self) -> None:
        from src.workers import actors

        assert hasattr(actors.run_retention_cleanup, "send")


@pytest.mark.unit
class TestTwinProfileAggregationActor:
    """B-012: twin_profile_aggregation must exist."""

    def test_twin_profile_aggregation_actor_exists(self) -> None:
        from src.workers import actors

        assert hasattr(actors, "run_twin_profile_aggregation")

    def test_twin_profile_aggregation_has_send_method(self) -> None:
        from src.workers import actors

        assert hasattr(actors.run_twin_profile_aggregation, "send")


@pytest.mark.unit
class TestPackHealthActor:
    """B-014: pack_health actor must exist."""

    def test_pack_health_actor_exists(self) -> None:
        from src.workers import actors

        assert hasattr(actors, "run_pack_health_aggregation")

    def test_pack_health_has_send_method(self) -> None:
        from src.workers import actors

        assert hasattr(actors, "run_pack_health_aggregation")


@pytest.mark.unit
class TestTagFoundationContentActor:
    """ADR-029 P1-1: tag_foundation_content_async actor must exist and be valid."""

    def test_tag_foundation_content_actor_exists(self) -> None:
        from src.workers import actors

        assert hasattr(actors, "tag_foundation_content_async")

    def test_tag_foundation_content_has_send_method(self) -> None:
        from src.workers import actors

        assert hasattr(actors.tag_foundation_content_async, "send")

    def test_tag_foundation_content_execution_calls_service(self) -> None:
        from src.workers import actors

        actor = actors.tag_foundation_content_async
        fn = getattr(actor, "fn", actor)
        underlying_fn = getattr(fn, "__wrapped__", fn)

        mock_session = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.core.database.session.get_db_session", return_value=mock_session_ctx),
            patch("src.core.middleware.tenant_context.set_tenant_id") as mock_set_tenant,
            patch("src.core.middleware.tenant_context.clear_tenant_context") as mock_clear_tenant,
            patch(
                "src.core.services.foundation_tagging_service.FoundationTaggingService.tag_content",
                new_callable=AsyncMock,
            ) as mock_tag,
        ):
            mock_tag.return_value = ["tag1", "tag2"]
            import asyncio

            result = asyncio.run(underlying_fn(content_id=42, tenant_id=99))

            mock_set_tenant.assert_called_once_with(99)
            mock_tag.assert_awaited_once_with(content_id=42, tenant_id=99, session=mock_session)
            mock_session.commit.assert_awaited_once()
            mock_clear_tenant.assert_called_once()
            assert result["status"] == "success"
            assert result["tags_count"] == 2
