# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
from typing import Any

from fastapi import APIRouter, HTTPException

from src.core.memory.event_bus import Event, event_bus
import logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/latest", response_model=list[dict[str, Any]])  # TODO(TYPE): replace Any with concrete type
async def get_latest_events(limit: int = 50) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Returns the last N events from the OODA EventBus.
    Used by the Frontend Mission Control Dashboard.
    """
    events = event_bus.get_recent_events(limit)
    # Convert Pydantic models to dicts for JSON response
    return [event.model_dump() for event in events]


@router.post("/events/publish", response_model=dict[str, str])
async def publish_manual_event(event_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Allow manual injection of events (e.g. from Webhooks, Testing, or External Sensors).
    """
    try:
        # Validate input using Pydantic model
        event = Event(**event_data)
        event_id = await event_bus.publish(event)
        return {"status": "published", "event_id": event_id}
    except Exception as e:
        logger.error("publish_manual_event mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=400, detail="Ongeldig verzoek.")
