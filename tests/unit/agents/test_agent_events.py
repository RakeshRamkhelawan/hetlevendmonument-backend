"""
SP-AGT-004 Dag 3 -- Agent event-bus Protocol tests.

Test taxonomy:
  3.1 -- module importeerbaar
  3.2 -- AgentCapabilityRegistered heeft verplichte velden
  3.3 -- IEventBus Protocol heeft publish methode
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_agent_events_module_importable() -> None:
    """src.core.shared.events.agent_events is importeerbaar -- SP-AGT-004 Dag 3."""
    from src.core.shared.events import agent_events  # noqa: F401

    assert agent_events is not None


@pytest.mark.unit
def test_agent_capability_registered_event_has_required_fields() -> None:
    """AgentCapabilityRegistered heeft tenant_id en capability_name -- SP-AGT-004 Dag 3."""
    from src.core.shared.events.agent_events import AgentCapabilityRegistered

    event = AgentCapabilityRegistered(
        tenant_id=1,
        capability_name="summarize",
        agent_id="agent-a1",
    )
    assert event.tenant_id == 1
    assert event.capability_name == "summarize"
    assert event.agent_id == "agent-a1"


@pytest.mark.unit
def test_ievent_bus_protocol_has_publish_method() -> None:
    """IEventBus Protocol heeft een publish methode -- SP-AGT-004 Dag 3."""
    from src.core.shared.events.agent_events import IEventBus

    assert hasattr(IEventBus, "publish"), "IEventBus moet een 'publish' methode hebben"
