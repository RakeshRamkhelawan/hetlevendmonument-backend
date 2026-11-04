"""
Tests for Redis Pub/Sub Event Consumer (ADR-006)
Vervangt de vorige RabbitMQ-gebaseerde consumer tests.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.events.consumer import EventConsumer, get_event_consumer


@pytest.fixture
def mock_pubsub_manager():
    """Mock Redis pub/sub manager"""
    manager = AsyncMock()
    manager.publish = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def event_consumer(mock_pubsub_manager):
    """Maak een event consumer met gemockte dependencies"""
    return EventConsumer(pubsub_manager=mock_pubsub_manager)


class TestEventConsumerInitialization:
    """Test EventConsumer initialisatie"""

    def test_consumer_initialization(self, event_consumer):
        """Test consumer initialiseert correct"""
        assert event_consumer._connected is False
        assert event_consumer._consuming is False
        assert event_consumer._handlers == {}

    def test_consumer_initialization_without_pubsub(self):
        """Test consumer initialiseert zonder pubsub_manager"""
        consumer = EventConsumer()
        assert consumer._connected is False
        assert consumer.pubsub_manager is None

    def test_consumer_ignores_redis_url(self):
        """Test dat redis_url parameter genegeerd wordt (backward-compat)"""
        consumer = EventConsumer(redis_url="redis://ignored:6379/0")
        assert consumer._connected is False


class TestEventConsumerHandlerRegistration:
    """Test handler registratie"""

    def test_register_handler(self, event_consumer):
        """Test registreren van event handlers"""
        mock_handler = AsyncMock()

        event_consumer.register_handler("agent.created", mock_handler)

        assert "agent.created" in event_consumer._handlers
        assert mock_handler in event_consumer._handlers["agent.created"]

    def test_register_multiple_handlers_same_event(self, event_consumer):
        """Test meerdere handlers registreren voor hetzelfde event"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        event_consumer.register_handler("workflow.completed", handler1)
        event_consumer.register_handler("workflow.completed", handler2)

        assert len(event_consumer._handlers["workflow.completed"]) == 2

    def test_unregister_handler(self, event_consumer):
        """Test verwijderen van een handler"""
        mock_handler = AsyncMock()

        event_consumer.register_handler("agent.created", mock_handler)
        event_consumer.unregister_handler("agent.created", mock_handler)

        assert mock_handler not in event_consumer._handlers["agent.created"]

    def test_unregister_nonexistent_handler(self, event_consumer):
        """Test verwijderen van niet-bestaande handler werkt zonder fout"""
        mock_handler = AsyncMock()
        # Geen exception verwacht
        event_consumer.unregister_handler("agent.created", mock_handler)


class TestEventConsumerConnect:
    """Test connect/disconnect logica"""

    @pytest.mark.asyncio
    async def test_connect_with_pubsub_manager(self, event_consumer):
        """Test verbinden met pubsub_manager slaagt"""
        await event_consumer.connect()
        assert event_consumer._connected is True

    @pytest.mark.asyncio
    async def test_connect_without_pubsub_manager(self):
        """Test verbinden zonder pubsub_manager haalt automatisch de singleton op"""
        from unittest.mock import AsyncMock, patch

        mock_manager = AsyncMock()
        with patch(
            "src.core.events.pubsub_manager.get_pubsub_manager",
            return_value=mock_manager,
        ):
            consumer = EventConsumer()
            await consumer.connect()
            assert consumer._connected is True
            assert consumer.pubsub_manager is mock_manager

    @pytest.mark.asyncio
    async def test_disconnect(self, event_consumer):
        """Test verbinding verbreken"""
        await event_consumer.connect()
        assert event_consumer._connected is True

        await event_consumer.disconnect()
        assert event_consumer._connected is False


class TestEventConsumerStats:
    """Test statistieken"""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, event_consumer):
        """Test stats zonder handlers"""
        stats = await event_consumer.get_stats()

        assert stats["connected"] is False
        assert stats["consuming"] is False
        assert stats["mode"] == "redis_pubsub"
        assert stats["total_handlers"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_handlers(self, event_consumer):
        """Test stats met geregistreerde handlers"""
        handler = AsyncMock()
        event_consumer.register_handler("agent.created", handler)
        event_consumer.register_handler("agent.created", handler)
        event_consumer.register_handler("workflow.completed", handler)

        stats = await event_consumer.get_stats()

        assert stats["total_handlers"] == 3
        assert stats["handlers_registered"]["agent.created"] == 2
        assert stats["handlers_registered"]["workflow.completed"] == 1


class TestEventConsumerSingleton:
    """Test singleton patroon"""

    @pytest.mark.asyncio
    @patch("src.core.events.consumer.EventConsumer")
    async def test_get_event_consumer_singleton(self, mock_consumer_class):
        """Test dat get_event_consumer een singleton retourneert"""
        import src.core.events.consumer as consumer_module

        consumer_module._event_consumer = None

        mock_instance = AsyncMock()
        mock_instance._connected = False
        mock_consumer_class.return_value = mock_instance

        consumer1 = await get_event_consumer()
        consumer2 = await get_event_consumer()

        assert consumer1 is consumer2
        mock_consumer_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_event_consumer_accepts_redis_url(self):
        """Test backward-compat: redis_url parameter wordt genegeerd"""
        import src.core.events.consumer as consumer_module

        consumer_module._event_consumer = None

        consumer = await get_event_consumer(redis_url="redis://ignored:6379")
        assert isinstance(consumer, EventConsumer)

        # Opruimen
        consumer_module._event_consumer = None
