"""Unit tests for Phase 1 -- calendar integrations.

Covers:
- TokenEncryptionService
- CalendarIntegration model
- CalendarIntegrationRepository (SQLite in-memory)
- GoogleCalendarProvider (mocked HTTP)
- OutlookCalendarProvider (mocked HTTP)
- CalendarSyncService (mocked providers)
- Integration API schemas
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database.database import Base
from src.core.models.rbac_models import Tenant  # noqa: F401
from src.core.scheduling.integrations.base_provider import (
    BaseCalendarProvider,
    ExternalEvent,
    OAuthTokens,
    SyncResult,
)
from src.core.scheduling.integrations.models import CalendarIntegration
from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
from src.core.scheduling.integrations.token_encryption import TokenEncryptionService
from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.schemas import (
    CalendarIntegrationResponse,
    ConnectProviderRequest,
    OAuthCallbackRequest,
    SyncStatusResponse,
)

TENANT_ID = 99
USER_ID = "user-abc"


# -- Fixtures ---------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Provide a fresh async session backed by in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:integ_test?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def encryption():
    return TokenEncryptionService(master_key="test-master-key-32chars-long!!!")


@pytest.fixture
def repo(db_session, encryption):
    return CalendarIntegrationRepository(db_session, encryption)


# =====================================================================
# TokenEncryptionService
# =====================================================================


class TestTokenEncryption:
    def test_encrypt_decrypt_roundtrip(self, encryption):
        plaintext = "ya29.very-secret-token"
        ciphertext = encryption.encrypt(plaintext)
        assert ciphertext != plaintext
        assert encryption.decrypt(ciphertext) == plaintext

    def test_different_keys_cannot_decrypt(self):
        enc1 = TokenEncryptionService(master_key="key-one-aaaaaaaaaaa")
        enc2 = TokenEncryptionService(master_key="key-two-bbbbbbbbbbb")

        ciphertext = enc1.encrypt("secret")
        with pytest.raises(Exception):
            enc2.decrypt(ciphertext)

    def test_empty_string_roundtrip(self, encryption):
        ct = encryption.encrypt("")
        assert encryption.decrypt(ct) == ""

    def test_long_token_roundtrip(self, encryption):
        long_token = "x" * 4096
        ct = encryption.encrypt(long_token)
        assert encryption.decrypt(ct) == long_token

    def test_ephemeral_key_when_no_env(self):
        with patch.dict("os.environ", {}, clear=False):
            # Remove MASTER_ENCRYPTION_KEY if it exists
            import os

            os.environ.pop("MASTER_ENCRYPTION_KEY", None)
            svc = TokenEncryptionService()
            ct = svc.encrypt("test")
            assert svc.decrypt(ct) == "test"


# =====================================================================
# CalendarIntegrationResponse schema
# =====================================================================


class TestIntegrationSchemas:
    def test_calendar_integration_response_from_attrs(self):
        obj = MagicMock()
        obj.id = "abc-123"
        obj.provider = "google"
        obj.provider_account_id = "acct-1"
        obj.provider_calendar_id = "primary"
        obj.is_active = True
        obj.last_synced_at = None
        obj.token_expires_at = None
        obj.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        resp = CalendarIntegrationResponse.model_validate(obj, from_attributes=True)
        assert resp.id == "abc-123"
        assert resp.provider == "google"
        assert resp.is_active is True

    def test_connect_provider_request_validation(self):
        req = ConnectProviderRequest(provider="google", redirect_uri="https://example.com/cb")
        assert req.provider == "google"

        with pytest.raises(Exception):
            ConnectProviderRequest(
                provider="unsupported",
                redirect_uri="https://x.com",
            )

    def test_oauth_callback_request_validation(self):
        req = OAuthCallbackRequest(code="4/0AX==", redirect_uri="https://example.com/cb")
        assert len(req.code) > 0

    def test_sync_status_response(self):
        resp = SyncStatusResponse(
            integration_id="int-1",
            provider="outlook",
            created=5,
            updated=2,
            deleted=1,
        )
        assert resp.created == 5
        assert resp.errors == []


# =====================================================================
# CalendarIntegrationRepository
# =====================================================================


class TestCalendarIntegrationRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="acct-goog",
            access_token="access-tok",
            refresh_token="refresh-tok",
        )
        assert integration.id is not None
        assert integration.provider == "google"
        assert integration.tenant_id == TENANT_ID

        # access_token_encrypted should NOT be the plaintext
        assert integration.access_token_encrypted != "access-tok"

        fetched = await repo.get_by_id(integration.id, TENANT_ID)
        assert fetched is not None
        assert fetched.id == integration.id

    @pytest.mark.asyncio
    async def test_get_by_user_provider(self, db_session, repo):
        await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="outlook",
            provider_account_id="acct-ms",
            access_token="tok1",
        )
        found = await repo.get_by_user_provider(TENANT_ID, USER_ID, "outlook")
        assert found is not None
        assert found.provider == "outlook"

        not_found = await repo.get_by_user_provider(TENANT_ID, USER_ID, "google")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_list_by_user(self, db_session, repo):
        await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="t1",
        )
        await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="outlook",
            provider_account_id="o1",
            access_token="t2",
        )
        items = await repo.list_by_user(TENANT_ID, USER_ID)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, db_session, repo):
        await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="t1",
        )
        # Different tenant should not see the integration
        items = await repo.list_by_user(TENANT_ID + 1, USER_ID)
        assert items == []

    @pytest.mark.asyncio
    async def test_update_tokens(self, db_session, repo, encryption):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="old-tok",
            refresh_token="old-ref",
        )
        new_expires = datetime(2026, 7, 1, tzinfo=timezone.utc)
        updated = await repo.update_tokens(
            integration,
            access_token="new-tok",
            refresh_token="new-ref",
            token_expires_at=new_expires,
        )
        assert repo.decrypt_access_token(updated) == "new-tok"
        assert repo.decrypt_refresh_token(updated) == "new-ref"
        # SQLite strips timezone info in datetime columns.
        assert updated.token_expires_at.replace(tzinfo=None) == new_expires.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_deactivate(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="t",
        )
        assert integration.is_active is True
        ok = await repo.deactivate(integration.id, TENANT_ID)
        assert ok is True
        fetched = await repo.get_by_id(integration.id, TENANT_ID)
        assert fetched.is_active is False

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="outlook",
            provider_account_id="o1",
            access_token="t",
        )
        ok = await repo.soft_delete(integration.id, TENANT_ID)
        assert ok is True

        # Should not be found anymore
        fetched = await repo.get_by_id(integration.id, TENANT_ID)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_get_any_by_user_provider_includes_soft_deleted(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="t",
        )

        await repo.soft_delete(integration.id, TENANT_ID)

        active = await repo.get_by_user_provider(TENANT_ID, USER_ID, "google")
        deleted = await repo.get_any_by_user_provider(TENANT_ID, USER_ID, "google")

        assert active is None
        assert deleted is not None
        assert deleted.id == integration.id
        assert deleted.is_deleted is True

    @pytest.mark.asyncio
    async def test_restore_and_update_revives_soft_deleted_integration(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="old-acct",
            access_token="old-token",
            refresh_token="old-refresh",
        )
        await repo.soft_delete(integration.id, TENANT_ID)

        deleted = await repo.get_any_by_user_provider(TENANT_ID, USER_ID, "google")
        restored = await repo.restore_and_update(
            deleted,
            provider_account_id="new-acct",
            access_token="new-token",
            refresh_token="new-refresh",
            token_expires_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            token_scope="calendar.readwrite",
        )

        assert restored.id == integration.id
        assert restored.is_deleted is False
        assert restored.is_active is True
        assert restored.provider_account_id == "new-acct"
        assert repo.decrypt_access_token(restored) == "new-token"
        assert repo.decrypt_refresh_token(restored) == "new-refresh"

    @pytest.mark.asyncio
    async def test_list_active_by_provider(self, db_session, repo):
        i1 = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="t",
        )
        await repo.create(
            tenant_id=TENANT_ID,
            user_id="user-2",
            provider="google",
            provider_account_id="g2",
            access_token="t2",
        )
        # Deactivate one
        await repo.deactivate(i1.id, TENANT_ID)

        active = await repo.list_active_by_provider(TENANT_ID, "google")
        assert len(active) == 1
        assert active[0].user_id == "user-2"

    @pytest.mark.asyncio
    async def test_update_sync_state(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="t",
        )
        assert integration.sync_token is None

        updated = await repo.update_sync_state(integration, sync_token="tok-abc")
        assert updated.sync_token == "tok-abc"
        assert updated.last_synced_at is not None

    @pytest.mark.asyncio
    async def test_decrypt_tokens(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="my-access",
            refresh_token="my-refresh",
        )
        assert repo.decrypt_access_token(integration) == "my-access"
        assert repo.decrypt_refresh_token(integration) == "my-refresh"

    @pytest.mark.asyncio
    async def test_decrypt_none_refresh_token(self, db_session, repo):
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="google",
            provider_account_id="g1",
            access_token="acc",
        )
        assert repo.decrypt_refresh_token(integration) is None


# =====================================================================
# GoogleCalendarProvider (mocked HTTP)
# =====================================================================


class TestGoogleCalendarProvider:
    @pytest.mark.asyncio
    async def test_exchange_code(self):
        from src.core.scheduling.integrations.google_calendar import GoogleCalendarProvider

        provider = GoogleCalendarProvider(client_id="test-client", client_secret="test-secret")

        token_response = {
            "access_token": "ya29.xxx",
            "refresh_token": "1//refresh",
            "expires_in": 3600,
            "scope": "calendar",
        }
        userinfo_response = {
            "id": "1234",
            "email": "user@gmail.com",
        }

        mock_resp_token = MagicMock()
        mock_resp_token.json.return_value = token_response
        mock_resp_token.status_code = 200
        mock_resp_token.raise_for_status = MagicMock()

        mock_resp_user = MagicMock()
        mock_resp_user.json.return_value = userinfo_response
        mock_resp_user.status_code = 200
        mock_resp_user.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_resp_token
            client_instance.get.return_value = mock_resp_user
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            tokens = await provider.exchange_code("auth-code", "https://example.com/cb")

        assert tokens.access_token == "ya29.xxx"
        assert tokens.refresh_token == "1//refresh"
        assert tokens.account_id == "1234"

    @pytest.mark.asyncio
    async def test_list_events_parses_items(self):
        from src.core.scheduling.integrations.google_calendar import GoogleCalendarProvider

        provider = GoogleCalendarProvider()

        api_response = {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Team standup",
                    "start": {
                        "dateTime": "2026-06-15T09:00:00Z",
                    },
                    "end": {
                        "dateTime": "2026-06-15T09:30:00Z",
                    },
                    "status": "confirmed",
                },
            ],
            "nextSyncToken": "sync-abc",
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            events, sync_tok = await provider.list_events(
                access_token="ya29.x",
                time_min=datetime(2026, 6, 1, tzinfo=timezone.utc),
                time_max=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

        assert len(events) == 1
        assert events[0].title == "Team standup"
        assert events[0].external_id == "evt-1"
        assert sync_tok == "sync-abc"


# =====================================================================
# OutlookCalendarProvider (mocked HTTP)
# =====================================================================


class TestOutlookCalendarProvider:
    @pytest.mark.asyncio
    async def test_exchange_code(self):
        from src.core.scheduling.integrations.outlook_calendar import OutlookCalendarProvider

        provider = OutlookCalendarProvider(client_id="ms-client", client_secret="ms-secret")

        token_response = {
            "access_token": "eyJ0xxx",
            "refresh_token": "0.xxx",
            "expires_in": 3600,
            "scope": "Calendars.ReadWrite",
        }
        user_response = {
            "id": "ms-user-id",
            "mail": "user@outlook.com",
        }

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_user_resp = MagicMock()
        mock_user_resp.json.return_value = user_response
        mock_user_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_token_resp
            client_instance.get.return_value = mock_user_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            tokens = await provider.exchange_code("auth-code", "https://example.com/cb")

        assert tokens.access_token == "eyJ0xxx"
        assert tokens.account_id == "ms-user-id"

    @pytest.mark.asyncio
    async def test_list_events_parses_graph_response(self):
        from src.core.scheduling.integrations.outlook_calendar import OutlookCalendarProvider

        provider = OutlookCalendarProvider()

        graph_response = {
            "value": [
                {
                    "id": "AAMk-1",
                    "subject": "1:1 with manager",
                    "start": {
                        "dateTime": "2026-06-15T14:00:00",
                        "timeZone": "UTC",
                    },
                    "end": {
                        "dateTime": "2026-06-15T14:30:00",
                        "timeZone": "UTC",
                    },
                    "showAs": "busy",
                    "isAllDay": False,
                    "attendees": [
                        {
                            "emailAddress": {
                                "address": "mgr@company.com",
                            },
                        },
                    ],
                },
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?tok=abc",
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = graph_response
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get.return_value = mock_resp
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            events, delta = await provider.list_events(
                access_token="eyJxxx",
                time_min=datetime(2026, 6, 1, tzinfo=timezone.utc),
                time_max=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

        assert len(events) == 1
        assert events[0].title == "1:1 with manager"
        assert events[0].attendees == ["mgr@company.com"]
        assert delta == "https://graph.microsoft.com/delta?tok=abc"


# =====================================================================
# CalendarSyncService
# =====================================================================


class _FakeProvider(BaseCalendarProvider):
    """Test stub that returns predetermined events."""

    provider_name = "fake"

    def __init__(
        self,
        events: Optional[List[ExternalEvent]] = None,
        sync_token: Optional[str] = "next-sync-tok",
    ) -> None:
        self._events = events or []
        self._sync_token = sync_token

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        return OAuthTokens(access_token="fake-at")

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        return OAuthTokens(
            access_token="refreshed-at",
            refresh_token=refresh_token,
        )

    async def list_events(
        self,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        sync_token: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> tuple[List[ExternalEvent], Optional[str]]:
        return self._events, self._sync_token

    async def create_event(
        self,
        access_token: str,
        event: ExternalEvent,
        calendar_id: str = "primary",
    ) -> str:
        return "ext-new-1"

    async def update_event(
        self,
        access_token: str,
        external_id: str,
        event: ExternalEvent,
        calendar_id: str = "primary",
    ) -> None:
        pass

    async def delete_event(
        self,
        access_token: str,
        external_id: str,
        calendar_id: str = "primary",
    ) -> None:
        pass

    async def get_user_info(self, access_token: str) -> Dict[str, str]:
        return {"id": "fake-id", "email": "fake@test.com"}


class TestCalendarSyncService:
    @pytest.mark.asyncio
    async def test_sync_creates_local_events(self, db_session, encryption):
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        ext_events = [
            ExternalEvent(
                external_id="ext-1",
                title="External Meeting",
                start_time=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc),
            ),
        ]
        fake = _FakeProvider(events=ext_events)
        repo = CalendarIntegrationRepository(db_session, encryption)

        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="fake",
            provider_account_id="fake-acct",
            access_token="at",
            refresh_token="rt",
            token_expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )

        svc = CalendarSyncService(
            db=db_session,
            providers={"fake": fake},
            integration_repo=repo,
        )

        result = await svc.sync_integration(integration)
        assert result.created == 1
        assert result.updated == 0
        assert result.next_sync_token == "next-sync-tok"

    @pytest.mark.asyncio
    async def test_sync_updates_existing_event(self, db_session, encryption):
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        # Create a local event that matches the external one
        local_event = CalendarEvent(
            tenant_id=TENANT_ID,
            title="Old Title",
            start_time=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc),
            organizer_id=USER_ID,
            event_type="external",
            status="confirmed",
            priority=3,
            metadata_json={
                "external_id": "ext-1",
                "provider": "fake",
            },
        )
        db_session.add(local_event)
        await db_session.flush()

        ext_events = [
            ExternalEvent(
                external_id="ext-1",
                title="Updated Title",
                start_time=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc),
            ),
        ]
        fake = _FakeProvider(events=ext_events)
        repo = CalendarIntegrationRepository(db_session, encryption)

        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="fake",
            provider_account_id="fa",
            access_token="at",
            token_expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )

        svc = CalendarSyncService(
            db=db_session,
            providers={"fake": fake},
            integration_repo=repo,
        )

        result = await svc.sync_integration(integration)
        assert result.updated == 1
        assert result.created == 0

    @pytest.mark.asyncio
    async def test_sync_soft_deletes_cancelled_external_event(self, db_session, encryption):
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        local_event = CalendarEvent(
            tenant_id=TENANT_ID,
            title="External Meeting",
            start_time=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc),
            organizer_id=USER_ID,
            event_type="external",
            status="confirmed",
            priority=3,
            metadata_json={
                "external_id": "ext-1",
                "provider": "fake",
            },
        )
        db_session.add(local_event)
        await db_session.flush()

        fake = _FakeProvider(
            events=[
                ExternalEvent(
                    external_id="ext-1",
                    title="External Meeting",
                    start_time=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                    end_time=datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc),
                    status="cancelled",
                    raw={"@removed": {"reason": "deleted"}},
                )
            ]
        )
        repo = CalendarIntegrationRepository(db_session, encryption)

        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="fake",
            provider_account_id="fa",
            access_token="at",
            token_expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )

        svc = CalendarSyncService(
            db=db_session,
            providers={"fake": fake},
            integration_repo=repo,
        )

        result = await svc.sync_integration(integration)

        assert result.deleted == 1
        assert local_event.is_deleted is True
        assert local_event.status == "cancelled"
        assert "external_deleted_at" in (local_event.metadata_json or {})

    @pytest.mark.asyncio
    async def test_sync_refreshes_expired_token(self, db_session, encryption):
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        fake = _FakeProvider(events=[])
        repo = CalendarIntegrationRepository(db_session, encryption)

        # Token already expired
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="fake",
            provider_account_id="fa",
            access_token="old-at",
            refresh_token="rt",
            token_expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )

        svc = CalendarSyncService(
            db=db_session,
            providers={"fake": fake},
            integration_repo=repo,
        )

        result = await svc.sync_integration(integration)
        assert result.errors == []

        # Token should have been refreshed
        assert repo.decrypt_access_token(integration) == "refreshed-at"

    @pytest.mark.asyncio
    async def test_push_event(self, db_session, encryption):
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        fake = _FakeProvider()
        repo = CalendarIntegrationRepository(db_session, encryption)

        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="fake",
            provider_account_id="fa",
            access_token="at",
            token_expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )

        local_event = CalendarEvent(
            tenant_id=TENANT_ID,
            title="Push Me",
            start_time=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
            organizer_id=USER_ID,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        db_session.add(local_event)
        await db_session.flush()

        svc = CalendarSyncService(
            db=db_session,
            providers={"fake": fake},
            integration_repo=repo,
        )

        ext_id = await svc.push_event(integration, local_event)
        assert ext_id == "ext-new-1"

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self, db_session, encryption):
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        repo = CalendarIntegrationRepository(db_session, encryption)
        integration = await repo.create(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider="unknown",
            provider_account_id="x",
            access_token="at",
        )

        svc = CalendarSyncService(db=db_session, providers={}, integration_repo=repo)

        with pytest.raises(ValueError, match="Unknown provider"):
            await svc.sync_integration(integration)


# =====================================================================
# ExternalEvent + OAuthTokens dataclasses
# =====================================================================


class TestDataclasses:
    def test_external_event_defaults(self):
        evt = ExternalEvent(
            external_id="e1",
            title="Test",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        )
        assert evt.attendees == []
        assert evt.status == "confirmed"
        assert evt.is_all_day is False
        assert evt.raw == {}

    def test_oauth_tokens_defaults(self):
        tok = OAuthTokens(access_token="at")
        assert tok.refresh_token is None
        assert tok.token_type == "Bearer"
        assert tok.account_id is None

    def test_sync_result_defaults(self):
        r = SyncResult()
        assert r.created == 0
        assert r.updated == 0
        assert r.deleted == 0
        assert r.errors == []
