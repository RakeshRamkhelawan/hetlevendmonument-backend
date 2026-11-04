"""
Tests voor src/core/events/publisher.py (Redis Pub/Sub implementatie, ADR-006)
Vervangt de vorige RabbitMQ/aio_pika-gebaseerde publisher tests.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.events.publisher import DomainEvent, EventPublisher, get_event_publisher
from src.core.events.pubsub_manager import EventType


class TestDomainEvent:
    """Test DomainEvent model"""

    def test_domain_event_creation(self):
        """Test DomainEvent aanmaken met verplichte velden"""
        event = DomainEvent(
            event_id="evt-123",
            event_type="test.event",
            aggregate_id="agg-456",
            aggregate_type="TestAggregate",
            data={"key": "value"},
        )

        assert event.event_id == "evt-123"
        assert event.event_type == "test.event"
        assert event.aggregate_id == "agg-456"
        assert event.aggregate_type == "TestAggregate"
        assert event.data == {"key": "value"}
        assert isinstance(event.timestamp, datetime)

    def test_domain_event_with_metadata(self):
        """Test DomainEvent met optionele metadata"""
        metadata = {"user_id": "user-1", "tenant_id": "tenant-1"}
        event = DomainEvent(
            event_id="evt-789",
            event_type="test.event",
            aggregate_id="agg-789",
            aggregate_type="Test",
            data={},
            metadata=metadata,
        )
        assert event.metadata == metadata

    def test_domain_event_timestamp_is_utc(self):
        """Test DomainEvent heeft UTC timestamp als standaard"""
        event = DomainEvent(
            event_id="evt-1",
            event_type="test",
            aggregate_id="agg-1",
            aggregate_type="Test",
            data={},
        )
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.tzinfo == timezone.utc


class TestEventPublisherInitialization:
    """Test EventPublisher initialisatie"""

    def test_initialization_without_pubsub(self):
        """Test EventPublisher initialiseert zonder pubsub_manager"""
        publisher = EventPublisher()
        assert publisher._pubsub_manager is None
        assert publisher._connected is False

    def test_initialization_with_pubsub(self):
        """Test EventPublisher initialiseert met pubsub_manager"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)
        assert publisher._pubsub_manager is mock_manager
        assert publisher._connected is False


class TestEventPublisherConnect:
    """Test EventPublisher.connect methode"""

    @pytest.mark.asyncio
    async def test_connect_success_with_provided_manager(self):
        """Test verbinden slaagt met een meegegeven pubsub_manager"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)

        await publisher.connect()

        assert publisher._connected is True
        assert publisher._pubsub_manager is mock_manager

    @pytest.mark.asyncio
    async def test_connect_fetches_global_manager_when_none(self):
        """Test verbinden haalt globale pubsub_manager op als niet opgegeven"""
        mock_manager = AsyncMock()
        publisher = EventPublisher()

        with patch(
            "src.core.events.publisher.get_pubsub_manager", return_value=mock_manager
        ) as mock_get:
            await publisher.connect()

        mock_get.assert_called_once()
        assert publisher._connected is True

    @pytest.mark.asyncio
    async def test_connect_failure_handled_gracefully(self):
        """Test verbindingsfout wordt afgehandeld zonder crash"""
        publisher = EventPublisher()

        with patch(
            "src.core.events.publisher.get_pubsub_manager",
            side_effect=Exception("Redis unavailable"),
        ):
            await publisher.connect()

        assert publisher._connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test verbinding verbreken"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)
        await publisher.connect()
        assert publisher._connected is True

        await publisher.disconnect()
        assert publisher._connected is False


class TestEventPublisherPublish:
    """Test EventPublisher.publish methode"""

    @pytest.mark.asyncio
    async def test_publish_success(self):
        """Test succesvol publiceren van een event"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)
        await publisher.connect()

        event = DomainEvent(
            event_id="evt-1",
            event_type="agent.created",
            aggregate_id="agg-1",
            aggregate_type="Agent",
            data={"tenant_id": 1},
        )

        await publisher.publish(event)

        mock_manager.publish.assert_called_once()
        message = mock_manager.publish.call_args[0][0]
        assert message.event_type == EventType.AGENT_REGISTERED

    @pytest.mark.asyncio
    async def test_publish_connects_when_not_connected(self):
        """Test publish maakt verbinding als dat nog niet gedaan is"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)
        assert publisher._connected is False

        event = DomainEvent(
            event_id="evt-1",
            event_type="agent.created",
            aggregate_id="agg-1",
            aggregate_type="Agent",
            data={},
        )

        await publisher.publish(event)

        assert publisher._connected is True
        mock_manager.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_with_custom_routing_key(self):
        """Test publiceren met aangepaste routing key"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)
        await publisher.connect()

        event = DomainEvent(
            event_id="evt-1",
            event_type="test.event",
            aggregate_id="agg-1",
            aggregate_type="Test",
            data={},
        )

        await publisher.publish(event, routing_key="workflow.started")

        message = mock_manager.publish.call_args[0][0]
        assert message.event_type == EventType.WORKFLOW_STARTED

    @pytest.mark.asyncio
    async def test_publish_warns_when_not_connected_after_connect_attempt(self):
        """Test publish logt waarschuwing als verbinding mislukt"""
        publisher = EventPublisher()
        publisher._connected = False  # geforceerd niet verbonden

        event = DomainEvent(
            event_id="evt-1",
            event_type="test",
            aggregate_id="agg-1",
            aggregate_type="Test",
            data={},
        )

        with patch.object(publisher, "connect", new=AsyncMock()):
            # Geen exception verwacht
            await publisher.publish(event)

    @pytest.mark.asyncio
    async def test_publish_unknown_event_type_maps_to_system_alert(self):
        """Test onbekend event type wordt gemapped naar SYSTEM_ALERT"""
        mock_manager = AsyncMock()
        publisher = EventPublisher(pubsub_manager=mock_manager)
        await publisher.connect()

        event = DomainEvent(
            event_id="evt-1",
            event_type="unknown.custom.event",
            aggregate_id="agg-1",
            aggregate_type="Custom",
            data={},
        )

        await publisher.publish(event)

        message = mock_manager.publish.call_args[0][0]
        assert message.event_type == EventType.SYSTEM_ALERT


class TestEventPublisherConvenienceMethods:
    """Test convenience publish methodes"""

    @pytest.mark.asyncio
    async def test_publish_agent_created(self):
        """Test publiceren van AgentCreated event"""
        publisher = EventPublisher()
        publisher.publish = AsyncMock()

        await publisher.publish_agent_created("agent-123", {"name": "Test"})

        event = publisher.publish.call_args[0][0]
        assert event.event_type == "agent.created"
        assert event.aggregate_id == "agent-123"
        assert event.aggregate_type == "Agent"

    @pytest.mark.asyncio
    async def test_publish_agent_updated(self):
        """Test publiceren van AgentUpdated event"""
        publisher = EventPublisher()
        publisher.publish = AsyncMock()

        await publisher.publish_agent_updated("agent-456", {"status": "active"})

        event = publisher.publish.call_args[0][0]
        assert event.event_type == "agent.updated"
        assert event.aggregate_id == "agent-456"

    @pytest.mark.asyncio
    async def test_publish_workflow_started(self):
        """Test publiceren van WorkflowStarted event"""
        publisher = EventPublisher()
        publisher.publish = AsyncMock()

        await publisher.publish_workflow_started("wf-123", {"name": "Workflow"})

        event = publisher.publish.call_args[0][0]
        assert event.event_type == "workflow.started"
        assert event.aggregate_type == "Workflow"

    @pytest.mark.asyncio
    async def test_publish_workflow_completed(self):
        """Test publiceren van WorkflowCompleted event"""
        publisher = EventPublisher()
        publisher.publish = AsyncMock()

        await publisher.publish_workflow_completed("wf-456", {"status": "success"})

        event = publisher.publish.call_args[0][0]
        assert event.event_type == "workflow.completed"

    @pytest.mark.asyncio
    async def test_publish_prediction_requested(self):
        """Test publiceren van PredictionRequested event"""
        publisher = EventPublisher()
        publisher.publish = AsyncMock()

        await publisher.publish_prediction_requested("req-789", {"model": "gpt-4"})

        event = publisher.publish.call_args[0][0]
        assert event.event_type == "ml.prediction_requested"
        assert event.aggregate_type == "MLPrediction"


class TestGetEventPublisher:
    """Test get_event_publisher functie"""

    @pytest.mark.asyncio
    async def test_get_event_publisher_creates_instance(self):
        """Test get_event_publisher maakt een instantie aan"""
        import src.core.events.publisher as publisher_module

        publisher_module._event_publisher = None

        with patch.object(EventPublisher, "connect", new=AsyncMock()):
            publisher = await get_event_publisher()

        assert publisher is not None
        assert isinstance(publisher, EventPublisher)
        publisher_module._event_publisher = None

    @pytest.mark.asyncio
    async def test_get_event_publisher_returns_singleton(self):
        """Test get_event_publisher retourneert dezelfde instantie"""
        import src.core.events.publisher as publisher_module

        publisher_module._event_publisher = None

        with patch.object(EventPublisher, "connect", new=AsyncMock()):
            pub1 = await get_event_publisher()
            pub2 = await get_event_publisher()

        assert pub1 is pub2
        publisher_module._event_publisher = None

    @pytest.mark.asyncio
    async def test_get_event_publisher_ignores_redis_url(self):
        """Test backward-compat: redis_url parameter wordt genegeerd"""
        import src.core.events.publisher as publisher_module

        publisher_module._event_publisher = None

        with patch.object(EventPublisher, "connect", new=AsyncMock()):
            publisher = await get_event_publisher(redis_url="amqp://ignored")

        assert isinstance(publisher, EventPublisher)
        publisher_module._event_publisher = None
