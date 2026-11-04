"""
Unit tests for OutlookCalendarProvider.

Uses respx to mock httpx HTTP calls to Microsoft Graph API.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import Response

import respx
from src.core.scheduling.integrations.base_provider import ExternalEvent
from src.core.scheduling.integrations.outlook_calendar import OutlookCalendarProvider


# Het neptoken dat de tests op de wire terugverwachten: de asserties op de
# Authorization-header vergelijken hiertegen, zodat "het token gaat mee" echt getoetst
# wordt en niet alleen "er is een header". Geen echte sleutel.
_BEARER = "test-bearer-waarde"


@pytest.fixture
def provider() -> OutlookCalendarProvider:
    """Create a provider with test credentials."""
    return OutlookCalendarProvider(
        client_id="test-client-id",
        client_secret="test-client-secret",
    )


class TestOutlookCalendarOAuth:
    """Tests for OAuth token exchange and refresh."""

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, provider: OutlookCalendarProvider) -> None:
        """Test successful OAuth code exchange."""

        @respx.mock
        async def inner_test() -> None:
            token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            respx.post(token_url).mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "new-access-token",
                        "refresh_token": "new-refresh-token",
                        "expires_in": 3600,
                        "scope": "Calendars.ReadWrite openid email profile",
                    },
                )
            )

            me_url = "https://graph.microsoft.com/v1.0/me"
            respx.get(me_url).mock(
                return_value=Response(
                    200,
                    json={
                        "id": "user-123",
                        "mail": "user@example.com",
                    },
                )
            )

            tokens = await provider.exchange_code(
                code="auth-code",
                redirect_uri="http://localhost/callback",
            )

            assert tokens.access_token == "new-access-token"
            assert tokens.refresh_token == "new-refresh-token"
            assert tokens.account_id == "user-123"
            assert tokens.expires_at is not None

        await inner_test()

    @pytest.mark.asyncio
    async def test_exchange_code_user_principal_name(
        self, provider: OutlookCalendarProvider
    ) -> None:
        """Test OAuth exchange when user has no mail but userPrincipalName."""

        @respx.mock
        async def inner_test() -> None:
            token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            respx.post(token_url).mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "new-access-token",
                        "expires_in": 3600,
                    },
                )
            )

            me_url = "https://graph.microsoft.com/v1.0/me"
            respx.get(me_url).mock(
                return_value=Response(
                    200,
                    json={
                        "id": "user-456",
                        "userPrincipalName": "user@tenant.onmicrosoft.com",
                    },
                )
            )

            tokens = await provider.exchange_code(
                code="auth-code",
                redirect_uri="http://localhost/callback",
            )

            assert tokens.account_id == "user-456"

        await inner_test()

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, provider: OutlookCalendarProvider) -> None:
        """Test successful token refresh."""

        @respx.mock
        async def inner_test() -> None:
            token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            respx.post(token_url).mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "refreshed-access-token",
                        "expires_in": 3600,
                    },
                )
            )

            tokens = await provider.refresh_access_token(refresh_token="old-refresh-token")

            assert tokens.access_token == "refreshed-access-token"
            assert tokens.expires_at is not None

        await inner_test()


class TestOutlookCalendarEvents:
    """Tests for event CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_events_success(self, provider: OutlookCalendarProvider) -> None:
        """Een enkele pagina met een event wordt naar ExternalEvent vertaald.

        Deze test stond uit met de reden "respx URL matching complexity with query params".
        Die beperking bestaat niet: `list_events` bouwt een URL met `startDateTime`,
        `endDateTime` en `$top` in de querystring, en respx matcht daarop met het
        `params`-patroon -- de volledige URL-string hoeft niet te kloppen (ADR-036 OP-196).

        LET OP: de payload hieronder gebruikt bewust `"timeZone": "UTC"`. Deze test dekt de
        TIJDZONEVERTALING dus NIET, en dat is geen slordigheid maar een afbakening:
        `_parse_event` gooit `timeZone` vandaag weg en stempelt alles UTC (13 uur mis bij
        Pacific/Auckland, gemeten). Dat is een eigen productiedefect met een eigen
        ontwerpvraag -- ADR-036 OP-238. Lees deze test niet als bewijs dat tijdzones kloppen.
        """

        @respx.mock
        async def inner_test() -> None:
            route = respx.get(
                "https://graph.microsoft.com/v1.0/me/calendarView",
                params__contains={"$top": "100"},
            ).mock(
                return_value=Response(
                    200,
                    json={
                        "value": [
                            {
                                "id": "event-abc",
                                "subject": "Kwartaaloverleg",
                                "start": {
                                    "dateTime": "2026-03-02T09:00:00",
                                    "timeZone": "UTC",
                                },
                                "end": {"dateTime": "2026-03-02T10:00:00", "timeZone": "UTC"},
                                "bodyPreview": "Cijfers doornemen",
                                "location": {"displayName": "Zaal 2"},
                                "organizer": {"emailAddress": {"address": "baas@example.com"}},
                                "attendees": [
                                    {"emailAddress": {"address": "een@example.com"}},
                                    {"emailAddress": {"address": "twee@example.com"}},
                                ],
                                "showAs": "busy",
                                "isAllDay": False,
                            }
                        ]
                    },
                )
            )

            time_min = datetime(2026, 3, 1, tzinfo=timezone.utc)
            time_max = datetime(2026, 3, 31, tzinfo=timezone.utc)
            events, next_delta = await provider.list_events(
                access_token=_BEARER,
                time_min=time_min,
                time_max=time_max,
            )

            assert route.called
            # Het VENSTER hoort op de wire te staan, niet alleen $top. Zonder deze twee
            # asserties bleef de test groen terwijl startDateTime/endDateTime uit de
            # opgebouwde URL waren gesloopt -- dan haalt een sync de HELE agenda op in
            # plaats van het gevraagde bereik (gemeten in de Gate 2-review, ADR-036 OP-196).
            params = route.calls[0].request.url.params
            # De `replace(" ", "+")` is geen slordigheid maar de kern van deze assertie.
            # `list_events` plakt `isoformat()` ongecodeerd in de querystring, en een `+`
            # betekent daar een SPATIE: de ontvangen waarde is vandaag
            # "2026-03-01T00:00:00 00:00" in plaats van "...+00:00". Dat is een echt defect
            # (ADR-036 OP-239), maar de spatie-vorm hoort NIET letterlijk in een assertie --
            # dan bewaakt deze test de bug en is terugdraaien de goedkoopste weg naar groen.
            # Deze vorm normaliseert de spatie terug en slaagt dus voor EN na die fix, terwijl
            # hij wel rood wordt als het venster verkeerd is OF de offset helemaal verdwijnt.
            # Dat laatste is precies wat een prefix-assertie zou laten glippen.
            assert params["startDateTime"].replace(" ", "+") == time_min.isoformat()
            assert params["endDateTime"].replace(" ", "+") == time_max.isoformat()
            # En het bearer-token hoort mee te gaan; zonder headers bleef de test ook groen.
            assert route.calls[0].request.headers["Authorization"] == "Bearer %s" % _BEARER

            assert len(events) == 1
            event = events[0]
            assert event.external_id == "event-abc"
            assert event.title == "Kwartaaloverleg"
            assert event.start_time == datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
            assert event.end_time == datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc)
            assert event.location == "Zaal 2"
            assert event.organizer_email == "baas@example.com"
            assert event.attendees == ["een@example.com", "twee@example.com"]
            assert next_delta is None

        await inner_test()

    @pytest.mark.asyncio
    async def test_list_events_with_delta(self, provider: OutlookCalendarProvider) -> None:
        """Test incremental sync using delta link."""

        @respx.mock
        async def inner_test() -> None:
            delta_url = (
                "https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken=old-token"
            )
            respx.get(delta_url).mock(
                return_value=Response(
                    200,
                    json={
                        "value": [],
                        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken=new-token",
                    },
                )
            )

            time_min = datetime(2026, 3, 1, tzinfo=timezone.utc)
            time_max = datetime(2026, 3, 31, tzinfo=timezone.utc)

            events, next_delta = await provider.list_events(
                access_token="test-token",
                time_min=time_min,
                time_max=time_max,
                sync_token=delta_url,
            )

            assert len(events) == 0
            assert (
                next_delta
                == "https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken=new-token"
            )

        await inner_test()

    @pytest.mark.asyncio
    async def test_list_events_pagination(self, provider: OutlookCalendarProvider) -> None:
        """De lus volgt `@odata.nextLink` en levert de events van BEIDE paginas.

        Deze test stond uit met de reden "respx URL matching complexity with pagination".
        Paginering bij Microsoft Graph houdt hetzelfde pad aan en wisselt alleen de
        querystring, dus twee opeenvolgende antwoorden op EEN route zijn precies wat respx
        met `side_effect=[...]` biedt (ADR-036 OP-196).

        De deltaLink wordt bewust alleen op de LAATSTE pagina meegegeven: `list_events`
        leest hem pas als er geen `nextLink` meer is.
        """

        @respx.mock
        async def inner_test() -> None:
            eerste_pagina = Response(
                200,
                json={
                    "value": [
                        {
                            "id": "event-1",
                            "subject": "Eerste",
                            "start": {"dateTime": "2026-03-02T09:00:00", "timeZone": "UTC"},
                            "end": {"dateTime": "2026-03-02T10:00:00", "timeZone": "UTC"},
                        }
                    ],
                    "@odata.nextLink": (
                        "https://graph.microsoft.com/v1.0/me/calendarView?$skiptoken=abc"
                    ),
                },
            )
            tweede_pagina = Response(
                200,
                json={
                    "value": [
                        {
                            "id": "event-2",
                            "subject": "Tweede",
                            "start": {"dateTime": "2026-03-03T09:00:00", "timeZone": "UTC"},
                            "end": {"dateTime": "2026-03-03T10:00:00", "timeZone": "UTC"},
                        }
                    ],
                    "@odata.deltaLink": (
                        "https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken=nieuw"
                    ),
                },
            )
            route = respx.get("https://graph.microsoft.com/v1.0/me/calendarView").mock(
                side_effect=[eerste_pagina, tweede_pagina]
            )

            events, next_delta = await provider.list_events(
                access_token=_BEARER,
                time_min=datetime(2026, 3, 1, tzinfo=timezone.utc),
                time_max=datetime(2026, 3, 31, tzinfo=timezone.utc),
            )

            assert route.call_count == 2
            # Het tweede verzoek moet naar de URL UIT de nextLink gaan. `side_effect` deelt
            # pagina 2 uit ongeacht welke URL wordt opgevraagd, dus zonder deze assertie
            # bleef de test groen terwijl de code een andere URL volgde -- in productie een
            # oneindige lus, want pagina 1 draagt altijd een nextLink (Gate 2-review,
            # ADR-036 OP-196).
            assert str(route.calls[1].request.url) == (
                "https://graph.microsoft.com/v1.0/me/calendarView?$skiptoken=abc"
            )
            assert [e.external_id for e in events] == ["event-1", "event-2"]
            assert next_delta == (
                "https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken=nieuw"
            )

        await inner_test()

    @pytest.mark.asyncio
    async def test_create_event_success(self, provider: OutlookCalendarProvider) -> None:
        """Test creating an event on Outlook Calendar."""

        @respx.mock
        async def inner_test() -> None:
            events_url = "https://graph.microsoft.com/v1.0/me/events"
            respx.post(events_url).mock(
                return_value=Response(
                    201,
                    json={"id": "new-event-id"},
                )
            )

            from src.core.scheduling.integrations.base_provider import ExternalEvent

            event = ExternalEvent(
                external_id="",
                title="New Meeting",
                start_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
                description="Test description",
                location="Conference Room A",
            )

            event_id = await provider.create_event(
                access_token="test-token",
                event=event,
            )

            assert event_id == "new-event-id"

        await inner_test()

    @pytest.mark.asyncio
    async def test_update_event_success(self, provider: OutlookCalendarProvider) -> None:
        """Een wijziging gaat als PATCH naar het event-pad, met de titel in de body.

        Deze test stond uit met de reden "respx PATCH mocking complexity". respx heeft
        gewoon `respx.patch()`, net als de `respx.delete()` die de test hieronder al
        gebruikt (ADR-036 OP-196).
        """

        @respx.mock
        async def inner_test() -> None:
            route = respx.patch("https://graph.microsoft.com/v1.0/me/events/event-123").mock(
                return_value=Response(200, json={"id": "event-123"})
            )

            await provider.update_event(
                access_token=_BEARER,
                external_id="event-123",
                event=ExternalEvent(
                    external_id="event-123",
                    title="Gewijzigde titel",
                    start_time=datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc),
                    end_time=datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc),
                ),
            )

            assert route.call_count == 1
            assert route.calls[0].request.headers["Authorization"] == "Bearer %s" % _BEARER
            verzonden = json.loads(route.calls[0].request.content)
            assert verzonden["subject"] == "Gewijzigde titel"

        await inner_test()

    @pytest.mark.asyncio
    async def test_delete_event_success(self, provider: OutlookCalendarProvider) -> None:
        """Test deleting an event from Outlook Calendar."""

        @respx.mock
        async def inner_test() -> None:
            event_url = "https://graph.microsoft.com/v1.0/me/events/event-123"
            respx.delete(event_url).mock(return_value=Response(204))

            await provider.delete_event(
                access_token="test-token",
                external_id="event-123",
            )

        await inner_test()


class TestOutlookCalendarEventParsing:
    """Tests for event parsing edge cases."""

    def test_parse_event_with_attendees(self, provider: OutlookCalendarProvider) -> None:
        """Test parsing events with attendees."""
        item = {
            "id": "event-3",
            "subject": "Meeting with Attendees",
            "start": {"dateTime": "2026-03-20T10:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-03-20T11:00:00", "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": "attendee1@example.com"}},
                {"emailAddress": {"address": "attendee2@example.com"}},
            ],
        }

        event = provider._parse_event(item)

        assert event.attendees == ["attendee1@example.com", "attendee2@example.com"]

    def test_parse_event_no_title(self, provider: OutlookCalendarProvider) -> None:
        """Test parsing event without subject."""
        item = {
            "id": "event-4",
            "start": {"dateTime": "2026-03-20T10:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-03-20T11:00:00", "timeZone": "UTC"},
        }

        event = provider._parse_event(item)

        assert event.title == "(no title)"

    def test_parse_event_all_day(self, provider: OutlookCalendarProvider) -> None:
        """Test parsing all-day event."""
        item = {
            "id": "event-5",
            "subject": "Holiday",
            "start": {"dateTime": "2026-03-20T00:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-03-21T00:00:00", "timeZone": "UTC"},
            "isAllDay": True,
        }

        event = provider._parse_event(item)

        assert event.is_all_day is True
        assert event.title == "Holiday"

    def test_build_event_body_complete(self, provider: OutlookCalendarProvider) -> None:
        """Test building event body with all fields."""
        from src.core.scheduling.integrations.base_provider import ExternalEvent

        event = ExternalEvent(
            external_id="",
            title="Test Meeting",
            start_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
            description="Test description",
            location="Room A",
            attendees=["user1@example.com", "user2@example.com"],
        )

        body = provider._build_event_body(event)

        assert body["subject"] == "Test Meeting"
        assert body["body"]["content"] == "Test description"
        assert body["location"]["displayName"] == "Room A"
        assert len(body["attendees"]) == 2

    def test_calc_expires(self, provider: OutlookCalendarProvider) -> None:
        """Test _calc_expires helper method."""
        from datetime import timedelta

        # Test with valid expires_in
        expires = provider._calc_expires(3600)
        assert expires is not None
        now = datetime.now(tz=timezone.utc)
        assert expires > now
        assert expires < now + timedelta(seconds=3601)

        # Test with None
        assert provider._calc_expires(None) is None

        # Test with zero (falsy, returns None)
        assert provider._calc_expires(0) is None
