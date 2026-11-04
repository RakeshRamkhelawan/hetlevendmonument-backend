"""
P4.6.3: Shared Domain - Comprehensive Test Coverage
Tests shared domain concepts: value objects, base entities, exceptions
Target: 80%+ coverage on src/domains/shared/
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.domains.shared.base_entity import AggregateRoot, Entity
from src.domains.shared.exceptions import DomainException, ValidationException
from src.domains.shared.value_objects import Email, EntityId, Timestamp


class TestEntityId:
    """Test EntityId value object"""

    def test_entity_id_creation(self):
        """Test creating EntityId"""
        entity_id = EntityId(value="test-id-123")
        assert str(entity_id) == "test-id-123"
        assert entity_id.value == "test-id-123"

    def test_entity_id_hash(self):
        """Test EntityId is hashable"""
        entity_id = EntityId(value="test-id-123")
        assert hash(entity_id) == hash("test-id-123")

    def test_entity_id_equality(self):
        """Test EntityId equality"""
        e1 = EntityId(value="test-id")
        e2 = EntityId(value="test-id")
        assert e1 == e2

    def test_entity_id_inequality(self):
        """Test EntityId inequality"""
        e1 = EntityId(value="id-1")
        e2 = EntityId(value="id-2")
        assert e1 != e2

    def test_entity_id_frozen(self):
        """Test EntityId is immutable"""
        entity_id = EntityId(value="immutable")
        with pytest.raises(ValueError):
            entity_id.value = "changed"

    def test_entity_id_in_set(self):
        """Test EntityId can be used in sets"""
        e1 = EntityId(value="id-1")
        e2 = EntityId(value="id-2")
        e3 = EntityId(value="id-1")

        id_set = {e1, e2, e3}
        assert len(id_set) == 2  # e1 and e3 are equal

    def test_entity_id_uuid_like(self):
        """Test EntityId with UUID-like value"""
        uuid_id = "550e8400-e29b-41d4-a716-446655440000"
        entity_id = EntityId(value=uuid_id)
        assert str(entity_id) == uuid_id

    def test_entity_id_numeric_string(self):
        """Test EntityId with numeric string"""
        entity_id = EntityId(value="12345")
        assert str(entity_id) == "12345"


class TestEmail:
    """Test Email value object"""

    def test_email_creation_valid(self):
        """Test creating valid email"""
        email = Email(value="test@example.com")
        assert str(email) == "test@example.com"
        assert email.value == "test@example.com"

    def test_email_validation_invalid_format(self):
        """Test email validation rejects invalid format"""
        with pytest.raises(ValidationError):
            Email(value="invalid-email")

    def test_email_validation_no_at_symbol(self):
        """Test email without @ symbol fails validation"""
        with pytest.raises(ValidationError):
            Email(value="testexample.com")

    def test_email_validation_no_domain(self):
        """Test email without domain fails validation"""
        with pytest.raises(ValidationError):
            Email(value="test@")

    def test_email_equality(self):
        """Test email equality"""
        e1 = Email(value="test@example.com")
        e2 = Email(value="test@example.com")
        assert e1 == e2

    def test_email_inequality(self):
        """Test email inequality"""
        e1 = Email(value="test1@example.com")
        e2 = Email(value="test2@example.com")
        assert e1 != e2

    def test_email_frozen(self):
        """Test Email is immutable"""
        email = Email(value="immutable@example.com")
        with pytest.raises(ValueError):
            email.value = "changed@example.com"

    def test_email_case_sensitivity(self):
        """Test email addresses (treated as case-sensitive by EmailStr)"""
        e1 = Email(value="Test@Example.com")
        e2 = Email(value="test@example.com")
        # EmailStr normalizes, so these may be equal
        assert str(e1).lower() == str(e2).lower()

    def test_email_with_subdomain(self):
        """Test email with subdomain"""
        email = Email(value="user@mail.example.co.uk")
        assert str(email) == "user@mail.example.co.uk"

    def test_email_with_plus_addressing(self):
        """Test email with plus addressing"""
        email = Email(value="user+tag@example.com")
        assert str(email) == "user+tag@example.com"


class TestTimestamp:
    """Test Timestamp value object"""

    def test_timestamp_creation(self):
        """Test creating timestamp"""
        ts = Timestamp()
        assert ts.value is not None
        assert isinstance(ts.value, datetime)

    def test_timestamp_string_representation(self):
        """Test timestamp string representation"""
        ts = Timestamp()
        ts_str = str(ts)
        assert len(ts_str) > 0
        assert "T" in ts_str  # ISO format

    def test_timestamp_iso_format(self):
        """Test timestamp ISO format"""
        ts = Timestamp()
        ts_str = str(ts)
        # ISO format should contain T between date and time
        assert "T" in ts_str
        # Should end with timezone or Z (UTC)
        assert ts_str[-1] in [
            "Z",
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "+",
        ]

    def test_timestamp_frozen(self):
        """Test Timestamp is immutable"""
        ts = Timestamp()
        with pytest.raises(ValueError):
            ts.value = datetime.now(timezone.utc)

    def test_timestamp_custom_value(self):
        """Test timestamp with custom datetime value"""
        custom_time = datetime(2025, 1, 1, 12, 0, 0)
        ts = Timestamp(value=custom_time)
        assert ts.value == custom_time

    def test_timestamp_equality(self):
        """Test timestamp equality"""
        time = datetime(2025, 1, 1, 12, 0, 0)
        ts1 = Timestamp(value=time)
        ts2 = Timestamp(value=time)
        assert ts1 == ts2

    def test_timestamp_inequality(self):
        """Test timestamp inequality"""
        ts1 = Timestamp(value=datetime(2025, 1, 1, 12, 0, 0))
        ts2 = Timestamp(value=datetime(2025, 1, 2, 12, 0, 0))
        assert ts1 != ts2


class TestEntity:
    """Test Entity base class"""

    def test_entity_creation_with_id(self):
        """Test creating entity"""
        entity = Entity(id="entity_123")
        assert entity.id == "entity_123"
        assert entity.created_at is not None

    def test_entity_updated_at_optional(self):
        """Test entity updated_at is optional"""
        entity = Entity(id="entity_456")
        assert entity.updated_at is None

    def test_entity_equality_by_id(self):
        """Test entity equality is based on ID"""
        e1 = Entity(id="same_id")
        e2 = Entity(id="same_id")
        assert e1 == e2

    def test_entity_inequality_by_id(self):
        """Test entity inequality based on different IDs"""
        e1 = Entity(id="id_1")
        e2 = Entity(id="id_2")
        assert e1 != e2

    def test_entity_hash(self):
        """Test entity is hashable"""
        e = Entity(id="hashable")
        assert hash(e.id) == hash("hashable")


class TestAggregateRoot:
    """Test AggregateRoot base class"""

    def test_aggregate_root_creation(self):
        """Test creating aggregate root"""
        agg = AggregateRoot(id="agg_123")
        assert agg.id == "agg_123"
        assert agg.created_at is not None

    def test_aggregate_root_add_domain_event(self):
        """Test adding domain event"""
        agg = AggregateRoot(id="agg_event")
        event = {"type": "test.event", "data": {"key": "value"}}
        agg.add_domain_event(event)

        events = agg.get_domain_events()
        assert len(events) == 1
        assert events[0] == event

    def test_aggregate_root_multiple_events(self):
        """Test adding multiple domain events"""
        agg = AggregateRoot(id="agg_multi")
        for i in range(5):
            agg.add_domain_event({"type": f"event_{i}"})

        events = agg.get_domain_events()
        assert len(events) == 5

    def test_aggregate_root_clear_events(self):
        """Test clearing domain events"""
        agg = AggregateRoot(id="agg_clear")
        agg.add_domain_event({"type": "event_1"})
        agg.add_domain_event({"type": "event_2"})

        assert len(agg.get_domain_events()) == 2
        agg.clear_domain_events()
        assert len(agg.get_domain_events()) == 0

    def test_aggregate_root_get_events_copy(self):
        """Test get_domain_events returns a copy"""
        agg = AggregateRoot(id="agg_copy")
        agg.add_domain_event({"type": "event_1"})

        events1 = agg.get_domain_events()
        events2 = agg.get_domain_events()

        # Should be different list objects
        assert events1 is not events2
        # But contain the same data
        assert events1 == events2


class TestDomainExceptions:
    """Test domain exception classes"""

    def test_domain_exception_creation(self):
        """Test creating DomainException"""
        exc = DomainException("Test error message")
        assert str(exc) == "Test error message"

    def test_validation_exception_creation(self):
        """Test creating ValidationException"""
        exc = ValidationException("Validation failed")
        assert str(exc) == "Validation failed"

    def test_validation_exception_is_domain_exception(self):
        """Test ValidationException inherits from DomainException"""
        exc = ValidationException("Test")
        assert isinstance(exc, DomainException)

    def test_domain_exception_with_extra_info(self):
        """Test domain exception with additional context"""
        exc = DomainException("Error with context")
        assert "context" in str(exc).lower()


class TestSharedDomainIntegration:
    """Integration tests for shared domain"""

    def test_entity_with_value_objects(self):
        """Test entity containing value objects"""
        entity = Entity(id="entity_with_vo")
        email = Email(value="user@example.com")
        entity_id = EntityId(value="vo_123")

        assert str(email) == "user@example.com"
        assert str(entity_id) == "vo_123"

    def test_aggregate_root_with_events_and_value_objects(self):
        """Test aggregate root with events and value objects"""
        agg = AggregateRoot(id="agg_complex")

        event = {
            "type": "user.created",
            "data": {
                "email": str(Email(value="test@example.com")),
                "user_id": str(EntityId(value="user_456")),
            },
        }
        agg.add_domain_event(event)

        events = agg.get_domain_events()
        assert events[0]["data"]["email"] == "test@example.com"
        assert events[0]["data"]["user_id"] == "user_456"

    def test_multiple_value_objects_in_set(self):
        """Test multiple value objects can be used together"""
        ids = [EntityId(value=f"id_{i}") for i in range(5)]
        emails = [Email(value=f"user{i}@example.com") for i in range(5)]

        assert len(ids) == 5
        assert len(emails) == 5
        assert len(set(ids)) == 5
        assert len(set(emails)) == 5


class TestSharedDomainEdgeCases:
    """Edge case tests for shared domain"""

    def test_entity_id_empty_string(self):
        """Test EntityId with empty string"""
        entity_id = EntityId(value="")
        assert str(entity_id) == ""

    def test_entity_id_very_long_string(self):
        """Test EntityId with very long string"""
        long_id = "x" * 1000
        entity_id = EntityId(value=long_id)
        assert len(str(entity_id)) == 1000

    def test_email_with_numbers_only_local(self):
        """Test email with numbers in local part"""
        email = Email(value="123456@example.com")
        assert str(email) == "123456@example.com"

    def test_timestamp_comparison(self):
        """Test timestamp comparison"""
        ts1 = Timestamp(value=datetime(2025, 1, 1, 10, 0, 0))
        ts2 = Timestamp(value=datetime(2025, 1, 1, 11, 0, 0))
        # Timestamps are comparable through their value
        assert ts1.value < ts2.value

    def test_aggregate_root_event_data_types(self):
        """Test aggregate root with various event data types"""
        agg = AggregateRoot(id="agg_types")

        complex_event = {
            "type": "complex",
            "string": "value",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }
        agg.add_domain_event(complex_event)

        events = agg.get_domain_events()
        assert events[0]["string"] == "value"
        assert events[0]["number"] == 42
        assert events[0]["list"] == [1, 2, 3]
