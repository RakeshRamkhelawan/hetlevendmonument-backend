"""
SentimentAgent Routes - Converted to APIRouter for Unified Server
Transformed from standalone FastAPI app to modular router component
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Import de gecorrigeerde, asynchrone database-initialisatie

# Configureer logging
logger = logging.getLogger("sentiment_agent_router")

# Create APIRouter instead of FastAPI app
router = APIRouter(tags=["Sentiment Agent"])

# Agent configuratie
AGENT_ID = "sentiment_agent"


# --- Pydantic Modellen ---
class TaskExecutionRequest(BaseModel):
    task_id: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class TaskExecutionResponse(BaseModel):
    status: str
    result: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    message: str


# --- API Endpoints ---
@router.get("/")
async def sentiment_root() -> dict[str, object]:
    """Root endpoint voor sentiment agent health check"""
    return {
        "agent": "sentiment_agent",
        "status": "online",
        "version": "1.0.0",
        "endpoints": ["/execute_task"],
    }


@router.get("/health")
async def sentiment_health_check() -> dict[str, str]:
    """Health check endpoint voor Docker en monitoring."""
    return {"status": "healthy", "agent_id": AGENT_ID}


@router.post("/execute_task", response_model=TaskExecutionResponse)
async def execute_sentiment_task(request: TaskExecutionRequest) -> TaskExecutionResponse:
    """Accepteert en verwerkt sentiment analyse taken."""
    logger.info(f"Sentiment analyse taak ontvangen: {request.description}")

    action = request.parameters.get("action", "sentiment_analysis")

    try:
        if action == "sentiment_analysis":
            result = _handle_sentiment_analysis(request.parameters)
        else:
            raise HTTPException(status_code=400, detail=f"Onbekende actie: {action}")

        return TaskExecutionResponse(
            status="completed",
            result=result,
            message=f"Taak '{action}' succesvol uitgevoerd.",
        )
    except Exception as e:
        logger.error(f"Fout tijdens de uitvoering van taak '{action}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/status")
async def sentiment_agent_status() -> dict[str, object]:
    """Agent status endpoint"""
    return {
        "agent_id": "sentiment_agent",
        "agent_name": "Sentiment Agent",
        "agent_type": "sentiment_processor",
        "status": "online",
        "capabilities": ["sentiment_analysis", "text_processing"],
        "supported_task_types": ["sentiment_analysis"],
        "endpoints": {
            "execute_task": "/execute_task",
            "health": "/health",
            "status": "/status",
        },
        "version": "1.0.0",
    }


# --- Sentiment Analyse Logica (Hersteld) ---
def _handle_sentiment_analysis(params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Voert een simpele, trefwoord-gebaseerde sentimentanalyse uit."""
    text = params.get("text", "")
    if not text:
        raise ValueError("'text' is een vereiste parameter voor sentiment_analysis.")

    text_lower = text.lower()
    positive_words = [
        "goed",
        "geweldig",
        "uitstekend",
        "fantastisch",
        "blij",
        "liefde",
        "beste",
        "perfect",
    ]
    negative_words = [
        "slecht",
        "vreselijk",
        "afschuwelijk",
        "haat",
        "slechtste",
        "verdrietig",
        "boos",
    ]

    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)

    if positive_count > negative_count:
        sentiment = "positive"
        confidence = min(0.95, 0.5 + (positive_count * 0.1))
    elif negative_count > positive_count:
        sentiment = "negative"
        confidence = min(0.95, 0.5 + (negative_count * 0.1))
    else:
        sentiment = "neutral"
        confidence = 0.5

    logger.info(f"Sentiment analyse voltooid: {sentiment} (vertrouwen: {confidence:.2f})")

    return {
        "text": text,
        "sentiment": sentiment,
        "confidence": round(confidence, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
