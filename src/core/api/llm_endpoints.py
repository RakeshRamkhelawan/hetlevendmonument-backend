# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel


router = APIRouter(prefix="/llm", tags=["LLM"])


# Pydantic model for API response (mirrors generic ModelInfo)
class APIModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    capabilities: list[str]
    description: str
    context_window: int
    max_output_tokens: int


@router.get("/models", response_model=list[APIModelInfo])
async def get_available_models() -> list[APIModelInfo]:
    """
    Get list of available LLM models with capabilities and metadata.
    Use this to populate Model Selectors in the UI.
    """
    try:
        from src.core.llm.llm_service import get_llm_service

        service = await get_llm_service()

        models = service.get_models_info()
        return [
            APIModelInfo(
                id=m.id,
                name=m.name,
                provider=m.provider,
                capabilities=m.capabilities,
                description=m.description,
                context_window=m.context_window,
                max_output_tokens=m.max_output_tokens,
            )
            for m in models
        ]
    except Exception as e:
        logger.opt(exception=True).error("get_available_models mislukt: {}", type(e).__name__)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/status")
async def get_llm_status() -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Get detailed connectivity status of all LLM providers.
    """
    try:
        from src.core.llm.llm_service import get_llm_service

        service = await get_llm_service()
        return await service.test_connectivity()
    except Exception as e:
        import traceback

        logger.error(f"LLM Status Endpoint Failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")
