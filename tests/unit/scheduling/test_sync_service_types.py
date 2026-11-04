"""Tests for the calendar sync service type annotations."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.scheduling.integrations.base_provider import (
    BaseCalendarProvider,
    ExternalEvent,
    SyncResult,
)
from src.core.scheduling.integrations.models import CalendarIntegration
from src.core.scheduling.integrations.sync_service import CalendarSyncService
from src.core.scheduling.integrations.repository import CalendarIntegrationRepository


class TestCalendarSyncServiceTypes:
    """Test suite for CalendarSyncService type annotations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked AsyncSession."""
        return AsyncMock()

    @pytest.fixture
    def mock_provider(self):
        """Create a mocked BaseCalendarProvider."""
        provider = AsyncMock(spec=BaseCalendarProvider)
        provider.provider_name = "google"
        return provider

    @pytest.fixture
    def sync_service(self, mock_db, mock_provider):
        """Create a CalendarSyncService with mocked dependencies."""
        return CalendarSyncService(
            db=mock_db,
            providers={"google": mock_provider},
        )

    @pytest.fixture
    def mock_integration(self):
        """Create a mocked CalendarIntegration."""
        integration = MagicMock(spec=CalendarIntegration)
        integration.id = "integration_1"
        integration.tenant_id = 1
        integration.user_id = "user_1"
        integration.provider = "google"
        integration.provider_calendar_id = "primary"
        integration.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        integration.sync_token = None
        return integration

    @pytest.fixture
    def external_event(self):
        """Create an ExternalEvent instance."""
        return ExternalEvent(
            external_id="evt_123",
            title="Team Meeting",
            start_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
            description="Weekly sync",
            location="Conference Room A",
            organizer_email="organizer@example.com",
            attendees=["user1@example.com", "user2@example.com"],
            status="confirmed",
        )

    def test_get_provider_returns_correct_provider(self, sync_service, mock_provider):
        """Test _get_provider returns the correct provider instance."""
        provider = sync_service._get_provider("google")

        assert provider is mock_provider

    def test_get_provider_raises_for_unknown_provider(self, sync_service):
        """Test _get_provider raises ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            sync_service._get_provider("unknown")

    @pytest.mark.asyncio
    async def test_ensure_valid_token_returns_access_token(
        self, sync_service, mock_integration, mock_provider
    ):
        """Test _ensure_valid_token returns a string access token."""
        mock_integration.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(
            hours=1
        )
        sync_service._integ_repo.decrypt_access_token = MagicMock(
            return_value="access_token_123"
        )

        token = await sync_service._ensure_valid_token(mock_integration, mock_provider)

        assert isinstance(token, str)
        assert token == "access_token_123"

    @pytest.mark.asyncio
    async def test_is_deleted_external_event_with_cancelled_status(self):
        """Test _is_deleted_external_event detects cancelled status."""
        event = ExternalEvent(
            external_id="evt_456",
            title="Cancelled Event",
            start_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
            status="cancelled",
        )

        is_deleted = CalendarSyncService._is_deleted_external_event(event)

        assert is_deleted is True


class TestCalendarIntegrationRepositoryTypes:
    """Test suite for CalendarIntegrationRepository type annotations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked AsyncSession."""
        return AsyncMock()

    @pytest.fixture
    def repository(self, mock_db):
        """Create a CalendarIntegrationRepository with mocked DB."""
        return CalendarIntegrationRepository(db=mock_db)

    @pytest.fixture
    def mock_integration(self):
        """Create a mocked CalendarIntegration."""
        integration = MagicMock(spec=CalendarIntegration)
        integration.id = "integration_1"
        integration.tenant_id = 1
        integration.user_id = "user_1"
        integration.provider = "google"
        integration.access_token_encrypted = "encrypted_token"
        integration.refresh_token_encrypted = "encrypted_refresh"
        return integration

    def test_decrypt_access_token_returns_string(self, repository, mock_integration):
        """Test decrypt_access_token returns a string token."""
        repository._enc.decrypt = MagicMock(return_value="access_token_123")

        token = repository.decrypt_access_token(mock_integration)

        assert isinstance(token, str)
        assert token == "access_token_123"

    def test_decrypt_refresh_token_returns_none_when_not_encrypted(
        self, repository, mock_integration
    ):
        """Test decrypt_refresh_token returns None when not stored."""
        mock_integration.refresh_token_encrypted = None

        token = repository.decrypt_refresh_token(mock_integration)

        assert token is None
